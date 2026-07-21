from __future__ import annotations

import base64

import httpx
import pytest

from backend.agents.prompts import build_model_messages
from backend.agents.schemas.intake import IntakeOutput
from backend.providers.models.base import (
    ImageGenerationRequest,
    ModelCapability,
    TextGenerationRequest,
)
from backend.providers.models.errors import ProviderError
from backend.providers.models.factory import build_model_providers
from backend.providers.models.openrouter import (
    OpenRouterConfig,
    OpenRouterImageModelProvider,
    OpenRouterTextModelProvider,
)


def _config() -> OpenRouterConfig:
    return OpenRouterConfig(
        api_key="test-key",
        text_model="bytedance-seed/seed-2.0-mini",
        image_model="bytedance-seed/seedream-4.5",
    )


def test_openrouter_text_provider_maps_chat_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        body = __import__("json").loads(request.content)
        assert body["model"] == "bytedance-seed/seed-2.0-mini"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "id": "or-text-id",
                "model": "bytedance-seed/seed-2.0-mini",
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
                "usage": {"prompt_tokens": 5, "completion_tokens": 7},
            },
        )

    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterTextModelProvider(_config(), client=client)

    result = provider.generate_structured(
        TextGenerationRequest(
            request_id="request-text",
            capability=ModelCapability.INTAKE,
            prompt_version="intake-v1",
            messages=build_model_messages(ModelCapability.INTAKE, {"brand_spec": {}}),
            json_schema=IntakeOutput.model_json_schema(),
        )
    )

    assert result.provider == "openrouter"
    assert result.provider_request_id == "or-text-id"
    assert result.content_json["ready"] is True
    assert result.input_tokens == 5


def test_openrouter_image_provider_decodes_base64_image() -> None:
    png = b"\x89PNG\r\n\x1a\nmock"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/images"
        body = __import__("json").loads(request.content)
        assert body["model"] == "logo-image-model"
        assert body["size"] == "2048x2048"
        return httpx.Response(
            200,
            json={
                "id": "or-image-id",
                "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
            },
        )

    config = OpenRouterConfig(
        api_key="test-key",
        text_model="text-model",
        image_model="default-image-model",
        image_model_overrides={ModelCapability.LOGO: "logo-image-model"},
    )
    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterImageModelProvider(config, client=client)

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image",
            capability=ModelCapability.LOGO,
            prompt="logo preview",
        )
    )

    assert images[0].provider == "openrouter"
    assert images[0].model == "logo-image-model"
    assert images[0].content == png
    assert images[0].width == 2048
    assert images[0].height == 2048
    assert images[0].provider_request_id == "or-image-id:0"


def test_openrouter_image_provider_skips_references_without_resolver() -> None:
    png = b"\x89PNG\r\n\x1a\nmock"

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert "input_references" not in body
        return httpx.Response(
            200,
            json={
                "id": "or-image-no-ref-id",
                "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
            },
        )

    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterImageModelProvider(_config(), client=client)

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image",
            capability=ModelCapability.IP,
            prompt="ip preview",
            reference_artifact_ids=["artifact-id"],
        )
    )

    assert images[0].content == png


def test_openrouter_image_provider_sends_references_via_chat_completions() -> None:
    png = b"\x89PNG\r\n\x1a\nmock"
    reference_uri = "data:image/png;base64,QUFBQQ=="

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        body = __import__("json").loads(request.content)
        assert body["model"] == "bytedance-seed/seedream-4.5"
        assert body["modalities"] == ["image", "text"]
        content = body["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "logo preview"}
        assert content[1] == {"type": "image_url", "image_url": {"url": reference_uri}}
        generated_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        return httpx.Response(
            200,
            json={
                "id": "or-multimodal-id",
                "model": "bytedance-seed/seedream-4.5",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "images": [
                                {"type": "image_url", "image_url": {"url": generated_uri}}
                            ],
                        }
                    }
                ],
            },
        )

    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterImageModelProvider(
        _config(),
        client=client,
        reference_image_resolver=lambda artifact_id: reference_uri,
    )

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image-ref",
            prompt="logo preview",
            reference_artifact_ids=["artifact-1"],
        )
    )

    assert len(images) == 1
    assert images[0].content == png
    assert images[0].mime_type == "image/png"
    assert images[0].provider_request_id == "or-multimodal-id:0"


def test_openrouter_error_detail_is_surfaced_and_sanitized() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "input_references is not a valid field"}},
        )

    client = httpx.Client(
        base_url="https://openrouter.ai/api/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterImageModelProvider(_config(), client=client)

    with pytest.raises(ProviderError) as caught:
        provider.generate(
            ImageGenerationRequest(request_id="request-image-error", prompt="logo preview")
        )

    assert "HTTP 400" in str(caught.value)
    assert "input_references is not a valid field" in str(caught.value)


def test_factory_accepts_openrouter_provider_pair(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_TEXT_MODEL", "bytedance-seed/seed-2.0-mini")
    monkeypatch.setenv("OPENROUTER_IMAGE_MODEL", "bytedance-seed/seedream-4.5")

    text_provider, image_provider = build_model_providers(
        text_provider_name="openrouter",
        image_provider_name="openrouter",
    )

    assert text_provider.provider_name == "openrouter"
    assert image_provider.provider_name == "openrouter"
