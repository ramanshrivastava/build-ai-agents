#!/bin/bash

# Test Anthropic API native structured output (no tools needed)
# Uses output_config.format with a JSON schema to enforce structured responses.
# Same question as test-no-tools.sh but with constrained decoding — Claude's
# response is guaranteed valid JSON matching the schema.
# Expected: stop_reason "end_turn", content[0].text is valid JSON (not free text).
# Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-structured-output.sh

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Error: ANTHROPIC_API_KEY is not set"
  echo "Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-structured-output.sh"
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
    ],
    "output_config": {
      "format": {
        "type": "json_schema",
        "schema": {
          "type": "object",
          "properties": {
            "city": { "type": "string" },
            "can_access_weather": { "type": "boolean" },
            "explanation": { "type": "string" }
          },
          "required": ["city", "can_access_weather", "explanation"],
          "additionalProperties": false
        }
      }
    }
  }' | jq .
