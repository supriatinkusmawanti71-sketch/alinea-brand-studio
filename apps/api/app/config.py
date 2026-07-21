from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "Brand Agent Studio"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    default_workspace_id: str = "local-workspace"
    default_actor_id: str = "local-developer"

    database_url: str = "postgresql://brand_agent:brand_agent@localhost:5432/brand_agent"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "brand-agent-local"
    s3_secret_access_key: str = "brand-agent-local-secret"
    s3_bucket: str = "brand-agent-local"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    text_model_provider: str = "fake"
    text_model_name: str = "fake-text-v1"
    image_model_provider: str = "fake"
    image_model_name: str = "fake-image-v1"
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_image_size: str = "1024x1024"
    siliconflow_art_director_text_model: str = ""
    siliconflow_logo_agent_text_model: str = ""
    siliconflow_ip_designer_text_model: str = ""
    siliconflow_directions_image_model: str = ""
    siliconflow_logo_image_model: str = ""
    siliconflow_ip_image_model: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_text_model: str = ""
    openrouter_image_model: str = ""
    openrouter_image_size: str = "2048x2048"
    openrouter_art_director_text_model: str = ""
    openrouter_logo_agent_text_model: str = ""
    openrouter_ip_designer_text_model: str = ""
    openrouter_directions_image_model: str = ""
    openrouter_logo_image_model: str = ""
    openrouter_ip_image_model: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_text_model: str = ""
    openai_image_model: str = ""
    openai_image_size: str = "1024x1024"
    openai_art_director_text_model: str = ""
    openai_logo_agent_text_model: str = ""
    openai_ip_designer_text_model: str = ""
    openai_directions_image_model: str = ""
    openai_logo_image_model: str = ""
    openai_ip_image_model: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
