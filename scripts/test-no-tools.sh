#!/bin/bash

# Test Anthropic API WITHOUT tool definitions
# Same question as test-tool-call-opus.sh but no tools array.
# Expected: stop_reason "end_turn" with a text response (no tool_use block).
# Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-no-tools.sh

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Error: ANTHROPIC_API_KEY is not set"
  echo "Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-no-tools.sh"
  exit 1
fi

curl -s https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 1024,
    "messages": [
      { "role": "user", "content": "What is the weather in Tokyo?" }
    ]
  }' | jq .
