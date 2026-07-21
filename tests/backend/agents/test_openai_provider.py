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
from backend.providers.models.errors import ProviderError, ProviderErrorCode
from backend.providers.models.factory import build_model_providers
from backend.providers.models.openai import (
    OpenAIConfig,
    OpenAIImageModelProvider,
    OpenAITextModelProvider,
)


def _config() -> OpenAIConfig:
    return OpenAIConfig(
        api_key="test-key",
        text_model="gpt-4.1-mini",
        image_model="gpt-image-2",
    )


def test_openai_text_provider_maps_chat_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        body = __import__("json").loads(request.content)
        assert body["model"] == "gpt-4.1-mini"
        assert body["response_format"] == {"type": "json_object"}
        assert "output_schema" in body["messages"][-1]["content"]
        return httpx.Response(
            200,
            json={
                "id": "openai-text-id",
                "model": "gpt-4.1-mini",
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
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAITextModelProvider(_config(), client=client)

    result = provider.generate_structured(
        TextGenerationRequest(
            request_id="request-text",
            capability=ModelCapability.INTAKE,
            prompt_version="intake-v1",
            messages=build_model_messages(ModelCapability.INTAKE, {"brand_spec": {}}),
            json_schema=IntakeOutput.model_json_schema(),
        )
    )

    assert result.provider == "openai"
    assert result.provider_request_id == "openai-text-id"
    assert result.content_json["ready"] is True
    assert result.input_tokens == 5


def test_openai_image_provider_decodes_base64_image() -> None:
    png = b"\x89PNG\r\n\x1a\nmock"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/generations"
        body = __import__("json").loads(request.content)
        assert body["model"] == "logo-image-model"
        assert body["size"] == "1024x1024"
        return httpx.Response(
            200,
            json={
                "id": "openai-image-id",
                "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
            },
        )

    config = OpenAIConfig(
        api_key="test-key",
        text_model="text-model",
        image_model="default-image-model",
        image_model_overrides={ModelCapability.LOGO: "logo-image-model"},
    )
    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAIImageModelProvider(config, client=client)

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image",
            capability=ModelCapability.LOGO,
            prompt="logo preview",
        )
    )

    assert images[0].provider == "openai"
    assert images[0].model == "logo-image-model"
    assert images[0].content == png
    assert images[0].width == 1024
    assert images[0].height == 1024
    assert images[0].provider_request_id == "openai-image-id:0"


def test_openai_image_provider_downloads_url_with_content_type() -> None:
    jpeg = b"\xff\xd8mock"
    seen_auth: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/images/generations":
            seen_auth["generations"] = request.headers.get("authorization")
            return httpx.Response(
                200,
                json={
                    "id": "openai-image-url-id",
                    "data": [{"url": "https://cdn.example/generated.jpg"}],
                },
            )
        assert str(request.url) == "https://cdn.example/generated.jpg"
        seen_auth["download"] = request.headers.get("authorization")
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=jpeg)

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAIImageModelProvider(_config(), client=client)

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image-url",
            capability=ModelCapability.DIRECTIONS,
            prompt="visual direction preview",
        )
    )

    assert images[0].content == jpeg
    assert images[0].mime_type == "image/jpeg"
    # The API call is authenticated, but the third-party CDN download must not
    # carry the provider key.
    assert seen_auth["generations"] == "Bearer test-key"
    assert seen_auth["download"] is None


def test_openai_image_provider_sends_references_via_images_edits() -> None:
    png = b"\x89PNG\r\n\x1a\ngenerated"
    reference_bytes = b"\x89PNG\r\n\x1a\nreference"
    reference_uri = "data:image/png;base64," + base64.b64encode(reference_bytes).decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/edits"
        content_type = request.headers.get("content-type", "")
        assert content_type.startswith("multipart/form-data")
        body = request.read()
        assert b'name="model"' in body
        assert b"gpt-image-2" in body
        assert b'filename="reference-0.png"' in body
        assert reference_bytes in body
        return httpx.Response(
            200,
            json={
                "id": "openai-edit-id",
                "data": [{"b64_json": base64.b64encode(png).decode("ascii")}],
            },
        )

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAIImageModelProvider(
        _config(),
        client=client,
        reference_image_resolver=lambda artifact_id: reference_uri,
    )

    images = provider.generate(
        ImageGenerationRequest(
            request_id="request-image-edit",
            capability=ModelCapability.IP,
            prompt="ip turnaround view",
            reference_artifact_ids=["artifact-1"],
        )
    )

    assert len(images) == 1
    assert images[0].content == png
    assert images[0].mime_type == "image/png"


def test_openai_provider_surfaces_safe_error_detail() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid image prompt; api_key=sk-testsecret123456 should not leak",
                    "type": "invalid_request_error",
                }
            },
        )

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAIImageModelProvider(_config(), client=client)

    with pytest.raises(ProviderError) as caught:
        provider.generate(
            ImageGenerationRequest(
                request_id="request-image-error",
                capability=ModelCapability.LOGO,
                prompt="logo preview",
            )
        )

    assert caught.value.code == ProviderErrorCode.CONTENT_REJECTED.value
    assert "Invalid image prompt" in str(caught.value)
    assert "sk-testsecret123456" not in str(caught.value)
    assert "api_key=***" in str(caught.value)


def test_openai_provider_treats_excessive_system_load_as_retryable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "excessive system load"}},
        )

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAIImageModelProvider(_config(), client=client)

    with pytest.raises(ProviderError) as caught:
        provider.generate(
            ImageGenerationRequest(
                request_id="request-image-overload",
                capability=ModelCapability.LOGO,
                prompt="logo preview",
            )
        )

    assert caught.value.code == ProviderErrorCode.UNAVAILABLE.value
    assert caught.value.retryable is True
    assert "excessive system load" in str(caught.value)


def test_openai_provider_treats_gateway_timeout_as_retryable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(504, text="Gateway Timeout")

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        headers={"Authorization": "Bearer test-key"},
        transport=httpx.MockTransport(handler),
    )
    provider = OpenAIImageModelProvider(_config(), client=client)

    with pytest.raises(ProviderError) as caught:
        provider.generate(
            ImageGenerationRequest(
                request_id="request-image-504",
                capability=ModelCapability.LOGO,
                prompt="logo preview",
            )
        )

    assert caught.value.code == ProviderErrorCode.TIMEOUT.value
    assert caught.value.retryable is True


def test_factory_accepts_openai_provider_pair(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-2")

    text_provider, image_provider = build_model_providers(
        text_provider_name="openai",
        image_provider_name="openai",
    )

    assert text_provider.provider_name == "openai"
    assert image_provider.provider_name == "openai"
