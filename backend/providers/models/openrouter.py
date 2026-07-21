from __future__ import annotations

import base64
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.providers.models.base import (
    GeneratedImage,
    ImageGenerationRequest,
    ModelCapability,
    TextGenerationRequest,
    TextGenerationResult,
)
from backend.providers.models.errors import ProviderError, ProviderErrorCode


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    text_model: str
    image_model: str
    base_url: str = "https://openrouter.ai/api/v1"
    image_size: str = "2048x2048"
    text_model_overrides: dict[ModelCapability, str] = field(default_factory=dict)
    image_model_overrides: dict[ModelCapability, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> OpenRouterConfig:
        required = {
            "api_key": os.getenv("OPENROUTER_API_KEY", "").strip(),
            "text_model": os.getenv("OPENROUTER_TEXT_MODEL", "").strip()
            or os.getenv("TEXT_MODEL_NAME", "").strip(),
            "image_model": os.getenv("OPENROUTER_IMAGE_MODEL", "").strip()
            or os.getenv("IMAGE_MODEL_NAME", "").strip(),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("Missing OpenRouter configuration: " + ", ".join(missing))
        return cls(
            **required,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            image_size=os.getenv("OPENROUTER_IMAGE_SIZE", "2048x2048"),
            text_model_overrides=_capability_model_overrides("TEXT_MODEL"),
            image_model_overrides=_capability_model_overrides("IMAGE_MODEL"),
        )

    def text_model_for(self, capability: ModelCapability) -> str:
        return self.text_model_overrides.get(capability, self.text_model)

    def image_model_for(self, capability: ModelCapability | None) -> str:
        if capability is None:
            return self.image_model
        return self.image_model_overrides.get(capability, self.image_model)


def _capability_model_overrides(kind: str) -> dict[ModelCapability, str]:
    env_names = {
        ModelCapability.INTAKE: (f"OPENROUTER_INTAKE_{kind}",),
        ModelCapability.DIRECTIONS: (
            f"OPENROUTER_ART_DIRECTOR_{kind}",
            f"OPENROUTER_DIRECTIONS_{kind}",
        ),
        ModelCapability.LOGO: (
            f"OPENROUTER_LOGO_AGENT_{kind}",
            f"OPENROUTER_LOGO_{kind}",
        ),
        ModelCapability.IP: (
            f"OPENROUTER_IP_DESIGNER_{kind}",
            f"OPENROUTER_IP_{kind}",
        ),
    }
    overrides: dict[ModelCapability, str] = {}
    for capability, names in env_names.items():
        for name in names:
            value = os.getenv(name, "").strip()
            if value:
                overrides[capability] = value
                break
    return overrides


class _OpenRouterClient:
    provider_name = "openrouter"

    def __init__(
        self,
        config: OpenRouterConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._client = client or httpx.Client(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8080",
                "X-Title": "Alinea Brand Workbench",
            },
        )

    def _post(self, path: str, *, json_body: dict[str, Any], timeout: int) -> httpx.Response:
        try:
            response = self._client.post(path, json=json_body, timeout=timeout)
        except httpx.TimeoutException as error:
            raise ProviderError(
                ProviderErrorCode.TIMEOUT,
                "OpenRouter 请求超时，请稍后重试。",
                retryable=True,
            ) from error
        except httpx.RequestError as error:
            raise ProviderError(
                ProviderErrorCode.UNAVAILABLE,
                "暂时无法连接 OpenRouter，请稍后重试。",
                retryable=True,
            ) from error
        if response.is_success:
            return response
        self._raise_for_response(response)

    @staticmethod
    def _safe_response_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            detail = response.text.strip()
        else:
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict):
                detail = (
                    error.get("message")
                    or error.get("detail")
                    or error.get("code")
                    or json.dumps(error, ensure_ascii=False, sort_keys=True)
                )
            elif isinstance(error, str):
                detail = error
            elif isinstance(payload, dict):
                detail_value = payload.get("message") or payload.get("detail")
                detail = (
                    detail_value
                    if isinstance(detail_value, str)
                    else json.dumps(payload, ensure_ascii=False, sort_keys=True)
                )
            else:
                detail = json.dumps(payload, ensure_ascii=False)

        detail = str(detail).strip()
        if not detail:
            return ""
        detail = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", detail)
        detail = re.sub(
            r"(?i)(authorization|api[_-]?key|token|bearer)\s*[:=]\s*[^\s,;}]+",
            r"\1=***",
            detail,
        )
        detail = " ".join(detail.split())
        return detail[:500]

    @classmethod
    def _raise_for_response(cls, response: httpx.Response) -> None:
        status = response.status_code
        if status in (401, 403):
            code, retryable = ProviderErrorCode.AUTH_FAILED, False
        elif status == 402:
            code, retryable = ProviderErrorCode.COST_LIMIT, False
        elif status == 429:
            code, retryable = ProviderErrorCode.RATE_LIMITED, True
        elif status in (408, 504):
            code, retryable = ProviderErrorCode.TIMEOUT, True
        elif status in (500, 502, 503):
            code, retryable = ProviderErrorCode.UNAVAILABLE, True
        else:
            code, retryable = ProviderErrorCode.CONTENT_REJECTED, False
        retry_after = response.headers.get("retry-after")
        message = f"OpenRouter 请求失败（HTTP {status}）。"
        detail = cls._safe_response_detail(response)
        if detail:
            message = f"{message} 上游返回：{detail}"
        raise ProviderError(
            code,
            message,
            retryable=retryable,
            retry_after_seconds=float(retry_after) if retry_after else None,
        )


class OpenRouterTextModelProvider(_OpenRouterClient):
    def __init__(
        self,
        config: OpenRouterConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(config, client=client)
        self.model_name = config.text_model

    def generate_structured(
        self,
        request: TextGenerationRequest,
    ) -> TextGenerationResult:
        started = time.monotonic()
        model_name = self.config.text_model_for(request.capability)
        messages = [message.model_dump(mode="json") for message in request.messages]
        messages[-1]["content"] += "\n\noutput_schema:\n" + json.dumps(
            request.json_schema,
            ensure_ascii=False,
            sort_keys=True,
        )
        response = self._post(
            "/chat/completions",
            json_body={
                "model": model_name,
                "messages": messages,
                "stream": False,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                # Cap output so OpenRouter's affordability pre-check reserves a
                # realistic amount instead of the model maximum (65k tokens).
                "max_tokens": 8_192,
            },
            timeout=request.timeout_seconds,
        )
        data = response.json()
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError(
                ProviderErrorCode.CONTENT_REJECTED,
                "OpenRouter 返回了无法识别的文本响应。",
                retryable=False,
            ) from error
        try:
            parsed_content: Any = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            parsed_content = content
        usage = data.get("usage") or {}
        return TextGenerationResult(
            provider=self.provider_name,
            model=data.get("model") or model_name,
            content_json=parsed_content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=int((time.monotonic() - started) * 1_000),
            provider_request_id=data.get("id") or request.request_id,
            finish_reason=choice.get("finish_reason") or "unknown",
        )


class OpenRouterImageModelProvider(_OpenRouterClient):
    def __init__(
        self,
        config: OpenRouterConfig,
        *,
        client: httpx.Client | None = None,
        reference_image_resolver: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(config, client=client)
        self.model_name = config.image_model
        self._reference_image_resolver = reference_image_resolver

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
        started = time.monotonic()
        model_name = self.config.image_model_for(request.capability)
        if request.reference_artifact_ids and self._reference_image_resolver is not None:
            # OpenRouter only accepts reference images through the multimodal
            # chat interface; the /images endpoint rejects unknown fields.
            return self._generate_with_references(request, model_name, started)
        json_body: dict[str, Any] = {
            "model": model_name,
            "prompt": request.prompt,
            "n": request.count,
            "size": self.config.image_size,
            "output_format": "png",
        }
        response = self._post(
            "/images",
            json_body=json_body,
            timeout=request.timeout_seconds,
        )
        data = response.json()
        image_items = data.get("data") or []
        if len(image_items) != request.count:
            raise ProviderError(
                ProviderErrorCode.CONTENT_REJECTED,
                "OpenRouter 返回的图片数量与请求不一致。",
                retryable=False,
            )
        try:
            width, height = (int(part) for part in self.config.image_size.split("x", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("OPENROUTER_IMAGE_SIZE must use WIDTHxHEIGHT") from error
        results: list[GeneratedImage] = []
        for index, item in enumerate(image_items):
            b64_json = item.get("b64_json")
            if not b64_json:
                raise ProviderError(
                    ProviderErrorCode.CONTENT_REJECTED,
                    "OpenRouter 图片响应缺少 b64_json。",
                    retryable=False,
                )
            results.append(
                GeneratedImage(
                    provider=self.provider_name,
                    model=model_name,
                    content=base64.b64decode(b64_json),
                    mime_type="image/png",
                    width=width,
                    height=height,
                    provider_request_id=f"{data.get('id') or request.request_id}:{index}",
                    latency_ms=int((time.monotonic() - started) * 1_000),
                )
            )
        return results

    def _generate_with_references(
        self,
        request: ImageGenerationRequest,
        model_name: str,
        started: float,
    ) -> list[GeneratedImage]:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        for artifact_id in request.reference_artifact_ids[:6]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._reference_image_resolver(artifact_id)},
                }
            )
        response = self._post(
            "/chat/completions",
            json_body={
                "model": model_name,
                "messages": [{"role": "user", "content": content}],
                "modalities": ["image", "text"],
            },
            timeout=request.timeout_seconds,
        )
        data = response.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError(
                ProviderErrorCode.CONTENT_REJECTED,
                "OpenRouter 返回了无法识别的多模态图片响应。",
                retryable=False,
            ) from error
        image_items = message.get("images") or []
        if len(image_items) != request.count:
            raise ProviderError(
                ProviderErrorCode.CONTENT_REJECTED,
                "OpenRouter 返回的图片数量与请求不一致。",
                retryable=False,
            )
        try:
            width, height = (int(part) for part in self.config.image_size.split("x", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("OPENROUTER_IMAGE_SIZE must use WIDTHxHEIGHT") from error
        results: list[GeneratedImage] = []
        for index, item in enumerate(image_items):
            image_url = (item.get("image_url") or {}).get("url") or item.get("url") or ""
            image_bytes, mime_type = self._decode_image_url(
                image_url,
                timeout=request.timeout_seconds,
            )
            results.append(
                GeneratedImage(
                    provider=self.provider_name,
                    model=data.get("model") or model_name,
                    content=image_bytes,
                    mime_type=mime_type,
                    width=width,
                    height=height,
                    provider_request_id=f"{data.get('id') or request.request_id}:{index}",
                    latency_ms=int((time.monotonic() - started) * 1_000),
                )
            )
        return results

    def _decode_image_url(self, image_url: str, *, timeout: int) -> tuple[bytes, str]:
        if image_url.startswith("data:"):
            header, _, payload = image_url.partition(",")
            if not payload:
                raise ProviderError(
                    ProviderErrorCode.CONTENT_REJECTED,
                    "OpenRouter 图片响应的 data URI 无效。",
                    retryable=False,
                )
            mime_type = header.removeprefix("data:").split(";", 1)[0].strip() or "image/png"
            return base64.b64decode(payload), mime_type
        if image_url.startswith(("http://", "https://")):
            try:
                # Strip the provider Authorization header so the API key is
                # never sent to a third-party image host.
                download_request = self._client.build_request("GET", image_url, timeout=timeout)
                download_request.headers.pop("Authorization", None)
                download = self._client.send(download_request, follow_redirects=True)
                download.raise_for_status()
            except httpx.TimeoutException as error:
                raise ProviderError(
                    ProviderErrorCode.TIMEOUT,
                    "OpenRouter 图片下载超时。",
                    retryable=True,
                ) from error
            except httpx.HTTPError as error:
                raise ProviderError(
                    ProviderErrorCode.UNAVAILABLE,
                    "OpenRouter 图片下载失败。",
                    retryable=True,
                ) from error
            mime_type = download.headers.get("content-type", "image/png").split(";", 1)[0].strip()
            return download.content, mime_type or "image/png"
        raise ProviderError(
            ProviderErrorCode.CONTENT_REJECTED,
            "OpenRouter 图片响应缺少可用的图片地址。",
            retryable=False,
        )
