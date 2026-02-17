"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-6"
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/build_ai_agents"
    debug: bool = False


settings = Settings()
