#!/bin/bash

# Test Anthropic tool calling API (Opus)
# Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-tool-call-opus.sh

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Error: ANTHROPIC_API_KEY is not set"
  echo "Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-tool-call-opus.sh"
  exit 1
fi

curl -s https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 1024,
    "tools": [
      {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "input_schema": {
          "type": "object",
          "properties": {
            "city": { "type": "string" }
          },
          "required": ["city"]
        }
      }
    ],
    "messages": [
      { "role": "user", "content": "What is the weather in Tokyo?" }
    ]
  }' | jq .
