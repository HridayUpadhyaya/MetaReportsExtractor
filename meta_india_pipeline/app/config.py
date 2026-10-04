from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Meta India Report Pipeline"
    database_url: str = "sqlite:///./meta_india.db"
    meta_hub_url: str = "https://transparency.meta.com/reports/regulatory-transparency-reports/"
    meta_country: str = "India"
    meta_download_delay_seconds: float = 2.5
    http_max_retries: int = 5
    playwright_fallback: bool = True

    bucket: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    region: str = "auto"
    endpoint: str | None = None

    ai_verify_enabled: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-5"
    ai_autofix: bool = False

    admin_token: str = "change-me"
    poll_seconds: int = 3


@lru_cache

def get_settings() -> Settings:
    return Settings()
