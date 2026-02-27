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

    # RAG / Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "clinical_guidelines"
    qdrant_api_key: str = ""

    # Google AI Embeddings
    # Set GOOGLE_API_KEY for API key auth, otherwise uses Vertex AI ADC.
    google_api_key: str = ""
    gcp_project_id: str = "raman-gcp-project-k8s-dev"
    gcp_location: str = "us-central1"
    embedding_model: str = "text-embedding-005"
    embedding_dimensions: int = 768


settings = Settings()
