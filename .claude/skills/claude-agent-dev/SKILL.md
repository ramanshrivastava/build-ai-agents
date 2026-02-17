---
name: claude-agent-dev
description: Claude Agent SDK patterns and best practices
---

# Claude Agent SDK Development Skill

## Package
```bash
uv add claude-agent-sdk
```

## Creating Custom Tools

Tools are deterministic Python functions the agent can call:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("tool_name", "Description of what it does", {"param": str})
async def my_tool(args: dict) -> dict:
    result = do_something(args["param"])
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(result)
        }]
    }

# Register tools as MCP server
tools_server = create_sdk_mcp_server(
    name="my_tools",
    version="1.0.0",
    tools=[my_tool]
)
```

## Tool Naming Convention
When referencing tools in allowed_tools:
```python
"mcp__<server_name>__<tool_name>"
# Example: "mcp__briefing__fetch_patient"
```

## Structured Output

Use JSON schema for validated output:

```python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",
        "schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string"}
            },
            "required": ["result"]
        }
    }
)
```

## Hooks for Observability

```python
from claude_agent_sdk import HookMatcher

async def log_hook(input_data, tool_use_id, context):
    print(f"Tool called: {input_data.get('tool_name')}")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [HookMatcher(hooks=[log_hook])],
        "PostToolUse": [HookMatcher(hooks=[log_hook])]
    }
)
```

## Query vs Client

- `query()` - One-off task, returns result
- `ClaudeSDKClient` - Continuous conversation with state

```python
from claude_agent_sdk import query

async for message in query(prompt="Do something", options=options):
    if hasattr(message, "structured_output"):
        return message.structured_output
```

## Testing Agents

NEVER call real LLM in tests. Always mock:

```python
@pytest.fixture
def mock_agent_response():
    return {"result": "mocked"}

async def test_agent(mock_agent_response, mocker):
    mocker.patch("claude_agent_sdk.query", return_value=[mock_agent_response])
    # ... test logic
```

## Langfuse Integration

```python
from langfuse import Langfuse

langfuse = Langfuse()

async def langfuse_hook(input_data, tool_use_id, context):
    langfuse.trace(
        name=f"tool:{input_data.get('tool_name')}",
        input=input_data.get('tool_input')
    )
    return {}
```

## SDK Version Compatibility
- Supports Python 3.10, 3.11, 3.12, 3.13
