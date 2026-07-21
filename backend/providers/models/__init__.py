"""Model-provider ports and deterministic development implementations."""

from backend.providers.models.base import (
    GeneratedImage,
    ImageGenerationRequest,
    ImageModelProvider,
    ModelCapability,
    ModelMessage,
    ModelRole,
    TextGenerationRequest,
    TextGenerationResult,
    TextModelProvider,
)
from backend.providers.models.errors import ProviderError, ProviderErrorCode
from backend.providers.models.factory import build_model_providers
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

__all__ = [
    "FakeImageModelProvider",
    "FakeTextModelProvider",
    "GeneratedImage",
    "ImageGenerationRequest",
    "ImageModelProvider",
    "ModelCapability",
    "ModelMessage",
    "ModelRole",
    "OpenAIConfig",
    "OpenAIImageModelProvider",
    "OpenAITextModelProvider",
    "OpenRouterConfig",
    "OpenRouterImageModelProvider",
    "OpenRouterTextModelProvider",
    "ProviderError",
    "ProviderErrorCode",
    "SiliconFlowConfig",
    "SiliconFlowImageModelProvider",
    "SiliconFlowTextModelProvider",
    "TextGenerationRequest",
    "TextGenerationResult",
    "TextModelProvider",
    "build_model_providers",
]
