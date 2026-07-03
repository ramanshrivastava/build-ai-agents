#!/usr/bin/env bash
#
# mcp-curl.sh — exercise the standalone FastMCP server over raw Streamable HTTP.
#
# MCP over HTTP is NOT plain REST: it requires an `Accept: application/json,
# text/event-stream` header, a stateful session handshake (initialize ->
# Mcp-Session-Id -> notifications/initialized), and returns Server-Sent Events.
# This script does all of that so you can prove the wire protocol in a demo.
#
# For everyday use prefer:  uv run fastmcp list  <url>
#                           uv run fastmcp call  <url> <tool> key=value
# Raw curl is only worth it to show the underlying protocol.
#
# Usage:
#   ./mcp-curl.sh                 # list tools
#   ./mcp-curl.sh call            # call search_clinical_guidelines (default query)
#   ./mcp-curl.sh call "warfarin interactions" 3
#
# Env:
#   MCP_URL    (default http://127.0.0.1:9000/mcp)
#   MCP_TOKEN  (optional; sent as Authorization: Bearer <token> if set)

set -euo pipefail

URL="${MCP_URL:-http://127.0.0.1:9000/mcp}"
CT="Content-Type: application/json"
ACCEPT="Accept: application/json, text/event-stream"

AUTH_ARGS=()
if [[ -n "${MCP_TOKEN:-}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${MCP_TOKEN}")
fi

# --- 1. initialize: capture the session id from the response headers ---------
SID=$(curl -s -D - -o /dev/null -X POST "$URL" \
  -H "$CT" -H "$ACCEPT" "${AUTH_ARGS[@]}" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"mcp-curl","version":"1"}}}' \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}')

if [[ -z "$SID" ]]; then
  echo "ERROR: no Mcp-Session-Id returned — is the server running at $URL ?" >&2
  exit 1
fi
echo "session: $SID" >&2

# --- 2. tell the server we finished initializing -----------------------------
curl -s -o /dev/null -X POST "$URL" \
  -H "$CT" -H "$ACCEPT" -H "Mcp-Session-Id: $SID" "${AUTH_ARGS[@]}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# --- 3. run the requested method; responses arrive as SSE 'data:' lines -------
mode="${1:-list}"
if [[ "$mode" == "call" ]]; then
  query="${2:-warfarin interactions}"
  max="${3:-3}"
  body=$(printf '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_clinical_guidelines","arguments":{"query":"%s","max_results":%s}}}' "$query" "$max")
else
  body='{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
fi

curl -s -N -X POST "$URL" \
  -H "$CT" -H "$ACCEPT" -H "Mcp-Session-Id: $SID" "${AUTH_ARGS[@]}" \
  -d "$body" \
  | grep '^data:' | sed 's/^data: //' | jq
