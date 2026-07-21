from __future__ import annotations

from backend.providers.models.fake import FakeImageModelProvider, FakeTextModelProvider
from backend.providers.models.openai import (
    OpenAIConfig,
    OpenAIImageModelProvider,
    OpenAITextModelProvider,
)
from backend.providers.models.openrouter import (
    OpenRouterConfig,
    OpenRouterImageModelProvider,
    OpenRouterTextModelProvider,
)
from backend.providers.models.siliconflow import (
    SiliconFlowConfig,
    SiliconFlowImageModelProvider,
    SiliconFlowTextModelProvider,
)


def build_model_providers(
    *,
    text_provider_name: str,
    image_provider_name: str,
    reference_image_resolver=None,
):
    """Build the unified text/image provider pair selected by application config."""

    normalized = (text_provider_name.lower(), image_provider_name.lower())
    if normalized == ("fake", "fake"):
        return FakeTextModelProvider(), FakeImageModelProvider()
    if normalized == ("siliconflow", "siliconflow"):
        config = SiliconFlowConfig.from_env()
        return SiliconFlowTextModelProvider(config), SiliconFlowImageModelProvider(
            config,
            reference_image_resolver=reference_image_resolver,
        )
    if normalized == ("openrouter", "openrouter"):
        config = OpenRouterConfig.from_env()
        return OpenRouterTextModelProvider(config), OpenRouterImageModelProvider(
            config,
            reference_image_resolver=reference_image_resolver,
        )
    if normalized == ("openai", "openai"):
        config = OpenAIConfig.from_env()
        return OpenAITextModelProvider(config), OpenAIImageModelProvider(
            config,
            reference_image_resolver=reference_image_resolver,
        )
    raise ValueError(
        "TEXT_MODEL_PROVIDER and IMAGE_MODEL_PROVIDER must both be fake, siliconflow, "
        "openrouter, or openai"
    )
