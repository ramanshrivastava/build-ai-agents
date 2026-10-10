"""Environment for the Claude Code CLI subprocess spawned by the Agent SDK.

Its own module (rather than living in briefing_agent) because every SDK path
needs it — including the V1 fallback in briefing_service, which briefing_agent
itself imports, so importing from briefing_agent there would be circular.
"""

from __future__ import annotations

from src.config import settings


def cli_env() -> dict[str, str]:
    """Env vars for the spawned Claude Code CLI subprocess: either direct
    Anthropic auth, or routing through the configured translation proxy (e.g.
    LiteLLM → Vertex Gemini).

    Without ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY is passed through so the CLI
    bills that key instead of the developer's Claude Code login (empty when no
    key is configured — the CLI then falls back to the login). pydantic-settings
    reads .env into Settings, NOT os.environ, so this explicit injection is
    required. With a proxy, the proxy branch mirrors the per-process env the
    `glm` shell function sets, and the real Anthropic key is deliberately NOT
    forwarded — the proxy only gets its own token. The SDK merges this over
    os.environ when spawning the CLI (`{**os.environ, **options.env}`), so it
    overrides cleanly without mutating the current process — which is also why
    the proxy branch blanks ANTHROPIC_API_KEY: omitting it would let a key
    exported in the backend's own environment through (the CLI treats "" as
    unset). Only the SDK paths use this; the Managed Agents path cannot be
    re-pointed (server-hosted by Anthropic).
    """
    if not settings.anthropic_base_url:
        if not settings.anthropic_api_key:
            return {}
        return {"ANTHROPIC_API_KEY": settings.anthropic_api_key}
    return {
        "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.anthropic_auth_token or "dummy",
        "ANTHROPIC_API_KEY": "",
        # Map every Claude tier the CLI may resolve internally onto the proxy
        # model name, so no background call escapes to real Anthropic.
        "ANTHROPIC_DEFAULT_OPUS_MODEL": settings.ai_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": settings.ai_model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": settings.ai_model,
    }
