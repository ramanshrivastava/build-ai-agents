"""FastMCP server exposing `search_clinical_guidelines` over Streamable HTTP.

Run standalone (from the `backend/` directory):

    uv run python -m mcp_server.server

The briefing agent connects to it via the Claude Agent SDK's external HTTP MCP
support (`{"type": "http", "url": ...}`). The tool logic is reused from
`src.services.rag_service` — this process is just a network transport in front of
the same Qdrant + Vertex embedding search the in-process tool uses.
"""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.server.auth.providers.debug import DebugTokenVerifier

from src.config import settings
from src.services.rag_service import async_search, format_as_xml_sources

logger = logging.getLogger(__name__)


def _build_auth() -> DebugTokenVerifier | None:
    """Return a static bearer-token verifier when a token is configured, else None.

    Simulates a third party gating its MCP server behind an API token. Off by
    default; enabled by setting `EXTERNAL_MCP_AUTH_TOKEN`.
    """
    token = settings.external_mcp_auth_token
    if not token:
        return None
    return DebugTokenVerifier(validate=lambda presented: presented == token)


mcp: FastMCP = FastMCP("clinical-guidelines", auth=_build_auth())


@mcp.tool
async def search_clinical_guidelines(
    query: str,
    specialty: str = "",
    max_results: int = 5,
) -> str:
    """Search clinical guidelines, drug interactions, and protocols.

    Returns relevant passages with source citations. Use this tool to find
    evidence-based recommendations for patient conditions and medications.
    """
    logger.info(
        "MCP tool call: search_clinical_guidelines(query=%r, specialty=%r, max_results=%d)",
        query,
        specialty,
        max_results,
    )
    results = await async_search(
        query=query,
        specialty=specialty or None,
        limit=max_results,
    )
    logger.info("MCP tool result: %d chunks returned", len(results))
    return format_as_xml_sources(results)


def main() -> None:
    """Run the server over Streamable HTTP."""
    logger.info(
        "Starting FastMCP server on http://%s:%d/mcp (auth=%s)",
        settings.mcp_server_host,
        settings.mcp_server_port,
        "on" if settings.external_mcp_auth_token else "off",
    )
    mcp.run(
        transport="http",
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
