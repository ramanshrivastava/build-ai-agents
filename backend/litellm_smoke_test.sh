#!/usr/bin/env bash
# Smoke-test the LiteLLM proxy in isolation: confirm it translates an Anthropic
# /v1/messages request into a Vertex Gemini call using your gcloud ADC credentials
# — WITHOUT involving the FastAPI backend. Run this after starting the proxy:
#
#   litellm --config backend/litellm.config.yaml --port 4000
#   bash backend/litellm_smoke_test.sh
#
# Override defaults if needed:
#   ANTHROPIC_BASE_URL=http://localhost:4000 AI_MODEL=gemini-3.1-pro-preview bash backend/litellm_smoke_test.sh
#
# What "pass" means: HTTP 200 + a reply, with `served model` showing the Gemini
# model — proving creds + Anthropic->Gemini translation both work.
set -euo pipefail

BASE_URL="${ANTHROPIC_BASE_URL:-http://localhost:4000}"
MODEL="${AI_MODEL:-gemini-3.1-pro-preview}"

echo "→ POST $BASE_URL/v1/messages  (requesting model=$MODEL)"

resp=$(curl -sS --max-time 60 -w '\n%{http_code}' \
  -X POST "$BASE_URL/v1/messages" \
  -H "content-type: application/json" \
  -H "x-api-key: dummy" \
  -H "anthropic-version: 2023-06-01" \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":64,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: OK\"}]}")

http_code=$(printf '%s\n' "$resp" | tail -n1)
body=$(printf '%s\n' "$resp" | sed '$d')

echo "HTTP status: $http_code"
if [ "$http_code" != "200" ]; then
  echo "✗ proxy returned non-200. Response body:"
  printf '%s\n' "$body"
  echo
  echo "Common causes:"
  echo "  - GOOGLE_APPLICATION_CREDENTIALS unset/wrong: export it to your"
  echo "    Vertex service-account JSON key:"
  echo "      export GOOGLE_APPLICATION_CREDENTIALS=\"/path/to/your/vertex-service-account.json\""
  echo "  - wrong project: check vertex_project in backend/litellm.config.yaml"
  echo "  - Vertex AI API not enabled in the project: gcloud services enable aiplatform.googleapis.com"
  exit 1
fi

printf '%s\n' "$body" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print("served model :", d.get("model"))
print("stop_reason  :", d.get("stop_reason"))
text = (d.get("content") or [{}])[0].get("text", "")
print("reply        :", text[:200])
'

echo "✓ LiteLLM -> Vertex Gemini translation works with your ADC credentials."
