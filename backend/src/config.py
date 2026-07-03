"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env")

    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-4-6"
    # Optional: route the SDK briefing agent through a translation proxy (e.g.
    # LiteLLM pointing at Vertex Gemini). When set, ai_model is the model NAME
    # the proxy expects (e.g. gemini-2.5-pro), not a real Claude id. Only the
    # in-process and HTTP-MCP SDK paths follow this; the Managed Agents path
    # stays on Anthropic (it is server-hosted and cannot be re-pointed).
    anthropic_base_url: str = ""
    anthropic_auth_token: str = ""
    # Extended-thinking token budget for the unified chat agent. 0 disables.
    # Sent as the Anthropic `thinking` param; for Gemini via LiteLLM this maps
    # to Vertex thinkingConfig (thinkingBudget + includeThoughts), which is
    # what makes the model's reasoning traces visible in the chat UI.
    ai_thinking_budget: int = 8192
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/build_ai_agents"
    debug: bool = False

    # Claude Managed Agents beta
    managed_agent_id: str = ""
    managed_environment_id: str = ""
    # Live runs of the briefing use ~8 tool calls in ~115s on a fresh session;
    # reused sessions with history need headroom on both budgets.
    managed_agent_session_timeout_seconds: int = 240
    managed_agent_max_tool_rounds: int = 16

    # RAG / Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "clinical_guidelines"
    qdrant_api_key: str = ""

    # Google AI Embeddings
    # Google API key for Vertex AI embeddings (required for RAG).
    google_api_key: str = ""
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    embedding_model: str = "text-embedding-005"
    embedding_dimensions: int = 768

    # External HTTP MCP server (third tool path; FastMCP over Streamable HTTP)
    # mcp_server_* configure the standalone server process (mcp_server/server.py);
    # external_mcp_url is where the agent connects to reach it.
    mcp_server_host: str = "127.0.0.1"
    mcp_server_port: int = 9000
    # Canonical FastMCP Streamable HTTP path is /mcp (no trailing slash); a
    # trailing slash 307-redirects, which the SDK's MCP client does not follow.
    external_mcp_url: str = "http://127.0.0.1:9000/mcp"
    external_mcp_auth_token: str = ""  # optional; sent as Authorization: Bearer ...


settings = Settings()
