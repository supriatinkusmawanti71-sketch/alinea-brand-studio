from __future__ import annotations

import httpx
import pytest

from backend.agents.prompts import build_model_messages
from backend.agents.schemas.intake import IntakeOutput
from backend.providers.models.base import (
    ImageGenerationRequest,
    ModelCapability,
    TextGenerationRequest,
)
from backend.providers.models.errors import ProviderError, ProviderErrorCode
from backend.providers.models.factory import build_model_providers
from backend.providers.models.siliconflow import (
    SiliconFlowConfig,
    SiliconFlowImageModelProvider,
    SiliconFlowTextModelProvider,
)


def _config() -> SiliconFlowConfig:
    return SiliconFlowConfig(
        api_key="test-key",
        text_model="test-text-model",
        image_model="test-image-model",
    )


def test_siliconflow_text_provider_maps_chat_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        body = __import__("json").loads(request.content)
        assert body["model"] == "test-text-model"
        assert body["response_format"] == {"type": "json_object"}
        assert "output_schema" in body["messages"][-1]["content"]
        return httpx.Response(
            200,
            headers={"x-siliconcloud-trace-id": "trace-text"},
            json={
                "id": "completion-id",
                "model": "test-text-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                '{"ready": true, "questions": [], '
                                '"brand_spec_patch": {}, "suggestions": [], '
                                '"conflicts": []}'
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    client = httpx.Client(
        base_url="https://api.siliconflow.cn/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = SiliconFlowTextModelProvider(_config(), client=client)
    request = TextGenerationRequest(
        request_id="request-text",
        capability=ModelCapability.INTAKE,
        prompt_version="intake-v1",
        messages=build_model_messages(ModelCapability.INTAKE, {"brand_spec": {}}),
        json_schema=IntakeOutput.model_json_schema(),
    )

    result = provider.generate_structured(request)

    assert result.provider == "siliconflow"
    assert result.provider_request_id == "trace-text"
    assert result.content_json["ready"] is True
    assert result.input_tokens == 12


def test_siliconflow_image_provider_downloads_expiring_url_immediately() -> None:
    png = b"\x89PNG\r\n\x1a\nmock"
    seen_auth: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/images/generations":
            body = __import__("json").loads(request.content)
            assert body["model"] == "test-image-model"
            assert body["batch_size"] == 1
            assert body["image"] == "https://assets.example/reference.png"
            return httpx.Response(
                200,
                headers={"x-siliconcloud-trace-id": "trace-image"},
                json={"images": [{"url": "https://cdn.example/generated.png"}]},
            )
        assert str(request.url) == "https://cdn.example/generated.png"
        seen_auth["download"] = request.headers.get("authorization")
        return httpx.Response(200, headers={"content-type": "image/png"}, content=png)

    client = httpx.Client(
        base_url="https://api.siliconflow.cn/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = SiliconFlowImageModelProvider(
        _config(),
        client=client,
        reference_image_resolver=lambda artifact_id: "https://assets.example/reference.png",
    )

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image",
            prompt="品牌方向图",
            reference_artifact_ids=["artifact-1"],
        )
    )

    assert len(images) == 1
    assert images[0].content == png
    assert images[0].width == 1024
    assert images[0].provider_request_id == "trace-image:0"
    # The third-party CDN download must not carry the provider key.
    assert seen_auth["download"] is None


def test_siliconflow_rate_limit_is_retryable() -> None:
    client = httpx.Client(
        base_url="https://api.siliconflow.cn/v1",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"retry-after": "2"})
        ),
    )
    provider = SiliconFlowTextModelProvider(_config(), client=client)
    request = TextGenerationRequest(
        request_id="request-rate-limit",
        capability=ModelCapability.INTAKE,
        prompt_version="intake-v1",
        messages=build_model_messages(ModelCapability.INTAKE, {"brand_spec": {}}),
        json_schema=IntakeOutput.model_json_schema(),
    )

    with pytest.raises(ProviderError) as caught:
        provider.generate_structured(request)

    assert caught.value.code == ProviderErrorCode.RATE_LIMITED.value
    assert caught.value.retryable is True
    assert caught.value.retry_after_seconds == 2


def test_siliconflow_text_provider_uses_capability_model_override() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["model"] == "art-director-model"
        return httpx.Response(
            200,
            json={
                "id": "completion-id",
                "model": "art-director-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                '{"ready": true, "questions": [], '
                                '"brand_spec_patch": {}, "suggestions": [], '
                                '"conflicts": []}'
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    config = SiliconFlowConfig(
        api_key="test-key",
        text_model="default-text-model",
        image_model="test-image-model",
        text_model_overrides={ModelCapability.DIRECTIONS: "art-director-model"},
    )
    client = httpx.Client(
        base_url="https://api.siliconflow.cn/v1",
        transport=httpx.MockTransport(handler),
    )
    provider = SiliconFlowTextModelProvider(config, client=client)

    result = provider.generate_structured(
        TextGenerationRequest(
            request_id="request-directions",
            capability=ModelCapability.DIRECTIONS,
            prompt_version="directions-v1",
            messages=build_model_messages(ModelCapability.DIRECTIONS, {"brand_spec": {}}),
            json_schema=IntakeOutput.model_json_schema(),
        )
    )

    assert result.model == "art-director-model"


def test_siliconflow_image_provider_uses_capability_model_override() -> None:
    png = b"\x89PNG\r\n\x1a\nmock"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/images/generations":
            body = __import__("json").loads(request.content)
            assert body["model"] == "logo-image-model"
            return httpx.Response(200, json={"images": [{"url": "https://cdn.example/logo.png"}]})
        return httpx.Response(200, headers={"content-type": "image/png"}, content=png)

    config = SiliconFlowConfig(
        api_key="test-key",
        text_model="test-text-model",
        image_model="default-image-model",
        image_model_overrides={ModelCapability.LOGO: "logo-image-model"},
    )
    client = httpx.Client(
        base_url="https://api.siliconflow.cn/v1",
        transport=httpx.MockTransport(handler),
    )
    provider = SiliconFlowImageModelProvider(config, client=client)

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-logo-image",
            capability=ModelCapability.LOGO,
            prompt="logo preview",
        )
    )

    assert images[0].model == "logo-image-model"


def test_factory_rejects_mixed_provider_configuration() -> None:
    with pytest.raises(ValueError, match="must both be fake, siliconflow, openrouter, or openai"):
        build_model_providers(
            text_provider_name="siliconflow",
            image_provider_name="fake",
        )
