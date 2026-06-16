# Clinical Guidelines MCP Server

A standalone [FastMCP](https://github.com/PrefectHQ/fastmcp) server that exposes the
`search_clinical_guidelines` tool over **Streamable HTTP**. It simulates a third-party-hosted
MCP server: the briefing agent connects to it remotely instead of running the tool in-process.

This is the **third tool path** for the briefing agent:

| Path | Mechanism | Where |
|------|-----------|-------|
| 1. In-process | `create_sdk_mcp_server()` (no transport) | `src/agents/briefing_agent.py` |
| 2. Managed | Anthropic Managed Agents custom tool | `src/services/managed_briefing_service.py` |
| **3. HTTP MCP** | **FastMCP over Streamable HTTP** | **this package** |

The search logic itself is **reused** from `src/services/rag_service.py` (Qdrant + Vertex
embeddings) — this process is purely a network transport in front of it.

> Architecture + sequence diagrams: [`docs/mcp-http-path.md`](../../docs/mcp-http-path.md)

## Why Streamable HTTP (not SSE)

SSE is deprecated in both FastMCP and the MCP spec (server→client streaming only). Streamable
HTTP is bidirectional, multi-client, and matches the Claude Agent SDK's `McpHttpServerConfig`
(`{"type": "http", "url": ...}`) natively.

## Run

From the `backend/` directory (so the `src` package resolves):

```bash
uv run python -m mcp_server.server
```

Serves at `http://127.0.0.1:9000/mcp` by default (no trailing slash — a trailing slash
307-redirects, which the SDK's MCP client does not follow). Configure via `.env`:

```
MCP_SERVER_HOST=127.0.0.1
MCP_SERVER_PORT=9000
EXTERNAL_MCP_URL=http://127.0.0.1:9000/mcp
EXTERNAL_MCP_AUTH_TOKEN=        # optional; when set, server requires Authorization: Bearer <token>
```

The server needs the same RAG config the backend uses (`QDRANT_URL`, `GOOGLE_API_KEY`,
`GCP_PROJECT_ID`, ...) since it calls the real search.

## Test in isolation

No network or agent required — FastMCP's in-memory transport connects a client straight to the
server object:

```python
from fastmcp import Client
from mcp_server.server import mcp

async with Client(mcp) as client:
    tools = await client.list_tools()
    result = await client.call_tool("search_clinical_guidelines", {"query": "metformin renal dosing"})
```

See `tests/test_mcp_server.py` for the full test (with `async_search` mocked, so no live Qdrant/Vertex).

## Wire to the agent

With the server running, call the dedicated endpoint:

```
POST /api/v1/patients/{id}/briefing/external-mcp
```

The agent (`generate_briefing_via_http_mcp` in `src/agents/briefing_agent.py`) builds a
`{"type": "http", "url": EXTERNAL_MCP_URL}` MCP config and lets the SDK route tool calls here over HTTP.
