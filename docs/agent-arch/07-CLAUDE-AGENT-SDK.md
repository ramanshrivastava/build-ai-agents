# Claude Agent SDK

**Part 8 of 8: Agent Architecture & AI Model Internals Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [What Is the Claude Agent SDK?](#1-what-is-the-claude-agent-sdk)
3. [Architecture: How the SDK Works Under the Hood](#2-architecture-how-the-sdk-works-under-the-hood)
4. [The query() Function](#3-the-query-function)
5. [Structured Output](#4-structured-output)
6. [Error Handling](#5-error-handling)
7. [Tool Creation (V2 Preview)](#6-tool-creation-v2-preview)
8. [Testing and Mocking](#7-testing-and-mocking)
9. [Permission Modes](#8-permission-modes)
10. [Hooks and Observability (V2 Preview)](#9-hooks-and-observability-v2-preview)
11. [Summary](#10-summary)

---

## Learning Objectives

After reading this document, you will understand:

- **Where** the Claude Agent SDK sits in the abstraction spectrum (raw API → SDK → framework) and why AI Doctor chose it
- **How** the SDK works under the hood — the CLI subprocess model, message flow, and why it does not call the API directly
- **What** `query()` does, parameter by parameter, and how async iteration works
- **How** structured output flows from a Pydantic model to a JSON Schema to a validated response
- **What** errors the SDK can throw and how to wrap them in domain-specific exceptions
- **How** to create custom tools for V2 using the `@tool` decorator and MCP server registration
- **How** to test agent code without calling a real LLM
- **When** to use each permission mode (`bypassPermissions`, `acceptEdits`, `default`, `plan`)
- **What** hooks enable for tool-level control and observability

Key mental models to internalize:

- The SDK is a **thin orchestration layer**. It manages the agentic loop so you do not have to, but it does not hide the API's semantics.
- `query()` is an **async generator**. Each `yield` is a message in the conversation — you iterate, not poll.
- **Structured output is enforced at the API level**, not parsed after the fact. The model is constrained to produce valid JSON matching your schema.

What this document is NOT:

- A framework comparison. Doc 02 covers that in the ["When to Use What" decision tree](02-TOOL-USE-AND-AGENTIC-LOOP.md#when-to-use-what) and the [comparison table](02-TOOL-USE-AND-AGENTIC-LOOP.md#comparison-table). This document goes deep on the SDK itself.
- A tutorial for the raw Anthropic API. Doc 01 covers [authentication](01-ANTHROPIC-API-FUNDAMENTALS.md#2-authentication), [messages](01-ANTHROPIC-API-FUNDAMENTALS.md#4-the-messages-array), and [parameters](01-ANTHROPIC-API-FUNDAMENTALS.md#7-configuration-parameters).

---

## 1. What Is the Claude Agent SDK?

The Claude Agent SDK is a Python (and TypeScript) library that sits between your application code and the Claude API. It automates the agentic loop — the cycle of sending a prompt, receiving a response, dispatching tool calls, and looping until done — while staying close enough to the API that you can reason about what is happening.

### Where It Sits

Doc 02 introduced three levels of abstraction for building with LLMs:

```
┌────────────────────────────────────────────────────────────┐
│  Level 1: Raw API (anthropic SDK)                          │
│  You write the loop. You dispatch tools. Full control.     │
├────────────────────────────────────────────────────────────┤
│  Level 2: Agent SDK (claude_agent_sdk)  ← YOU ARE HERE     │
│  Loop handled. Tools registered. Structured output built   │
│  in. Still single-provider, still close to the metal.      │
├────────────────────────────────────────────────────────────┤
│  Level 3: Framework (LangChain, LlamaIndex, CrewAI)        │
│  Multi-provider. Rich ecosystem. Heavy abstraction.        │
└────────────────────────────────────────────────────────────┘
```

### What the SDK Automates vs What You Still Control

| SDK Handles | You Control |
|-------------|-------------|
| Agentic loop (call → check → dispatch → repeat) | System prompt content |
| Tool dispatch and result routing | Which tools to register and allow |
| Structured output schema enforcement | Schema design (Pydantic models) |
| CLI process lifecycle | When to call `query()` and what prompt to send |
| Permission model enforcement | Which permission mode to use |
| Error propagation from CLI subprocess | How to handle each error type |
| Async iteration over message stream | Business logic for each message type |

### What This Document Covers vs Doc 02

Doc 02's coverage (~180 lines) answers **"why the SDK instead of alternatives?"** — positioning it in the framework landscape with a comparison table and decision tree.

This document answers **"how does the SDK actually work?"** — architecture, `query()` internals, structured output flow, error handling, tools, testing, permissions, and hooks. If Doc 02 is the menu, this document is the recipe.

---

## 2. Architecture: How the SDK Works Under the Hood

### The CLI Subprocess Model

The Claude Agent SDK does **not** make HTTP requests to `api.anthropic.com` directly. Instead, it spawns the **Claude Code CLI** as a child process and communicates via stdin/stdout:

```
┌──────────────────────┐
│   Your Application   │
│  (briefing_service)  │
└──────────┬───────────┘
           │  query(prompt, options)
           ▼
┌──────────────────────┐
│  Claude Agent SDK    │
│  (claude_agent_sdk)  │
│                      │
│  - Serializes options│
│  - Spawns subprocess │
│  - Parses JSON msgs  │
└──────────┬───────────┘
           │  stdin: JSON commands
           │  stdout: JSON messages
           ▼
┌──────────────────────┐
│  Claude Code CLI     │
│  (child process)     │
│                      │
│  - Manages API auth  │
│  - Runs agentic loop │
│  - Executes tools    │
│  - Enforces perms    │
└──────────┬───────────┘
           │  HTTPS
           ▼
┌──────────────────────┐
│  Anthropic Messages  │
│  API                 │
│  api.anthropic.com   │
└──────────────────────┘
```

### Why a Subprocess?

You might ask: why not just call the API directly like the `anthropic` Python SDK does?

1. **Tool execution environment.** The CLI provides a sandboxed environment where Claude can execute tools (Read files, run Bash commands, etc.). Your Python process does not need to implement a file reader or shell executor — the CLI already has them.

2. **Permission enforcement.** The CLI's permission model (which tools are allowed, which need human approval) is battle-tested. The SDK inherits this without reimplementing it.

3. **Auth delegation.** The CLI handles API key management, including reading from environment variables or the Claude Code configuration. Your code passes `model` and `system_prompt`, not API keys (though you can configure `ANTHROPIC_API_KEY` in your environment for production — see [`backend/src/config.py`](../../backend/src/config.py)).

4. **Consistent behavior.** The same agentic loop that powers `claude` on the command line powers your SDK calls. Bug fixes and improvements to the CLI propagate to the SDK automatically.

### Message Flow: The Full Round Trip

Here is what happens when you call `query()`:

```
Your Code                  SDK                    CLI Process              API
   │                        │                         │                    │
   │  query(prompt, opts)   │                         │                    │
   │───────────────────────>│                         │                    │
   │                        │  spawn subprocess       │                    │
   │                        │────────────────────────>│                    │
   │                        │  stdin: JSON config     │                    │
   │                        │────────────────────────>│                    │
   │                        │                         │  POST /messages    │
   │                        │                         │───────────────────>│
   │                        │                         │  200 OK + response │
   │                        │                         │<───────────────────│
   │                        │  stdout: JSON message   │                    │
   │                        │<────────────────────────│                    │
   │  yield AssistantMessage│                         │                    │
   │<───────────────────────│                         │                    │
   │                        │                         │                    │
   │  ... (tool calls if    │                         │                    │
   │   max_turns > 1) ...   │                         │                    │
   │                        │                         │                    │
   │                        │  stdout: result JSON    │                    │
   │                        │<────────────────────────│                    │
   │  yield ResultMessage   │                         │                    │
   │<───────────────────────│                         │                    │
   │                        │  process exits          │                    │
   │                        │<────────────────────────│                    │
   │  iteration ends        │                         │                    │
   │                        │                         │                    │
```

Key observations:

- **Async iteration.** Each `yield` corresponds to a message from the CLI's stdout. You process messages as they arrive, not all at once.
- **Process lifecycle.** The CLI process starts when `query()` begins iterating and exits when the conversation completes. One `query()` call = one subprocess.
- **JSON over pipes.** All communication between the SDK and CLI uses newline-delimited JSON over stdin/stdout. The SDK parses each line into typed Python objects (`AssistantMessage`, `ResultMessage`, etc.).

### System Prompt Placement

In Doc 01, we discussed how the raw API accepts a `system` parameter separate from the `messages` array. The SDK follows the same pattern:

```python
# SDK: system_prompt is a separate field, NOT a message
options = ClaudeAgentOptions(
    system_prompt="You are a clinical decision support assistant...",
)

# This becomes the "system" parameter in the API call.
# It is NOT injected into the messages array as {"role": "system", ...}.
```

This matters because the system prompt receives special treatment in the transformer's attention mechanism — it is always "visible" to the model without consuming a conversation turn. See Doc 01's discussion of [the system parameter](01-ANTHROPIC-API-FUNDAMENTALS.md#7-configuration-parameters) for details.

---

## 3. The query() Function

`query()` is the primary entry point for one-shot SDK interactions. It sends a prompt, runs the agentic loop, and yields messages as an async generator.

### Signature

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(prompt: str, options: ClaudeAgentOptions = None):
    # process each message
    ...
```

### ClaudeAgentOptions

The options object configures every aspect of the agent's behavior:

```python
options = ClaudeAgentOptions(
    system_prompt: str,           # System prompt (separate from messages)
    model: str,                   # Model ID: "claude-opus-4-6", "claude-sonnet-4-5-20250929"
    output_format: dict,          # Structured output schema (see Section 4)
    max_turns: int,               # Max agentic loop iterations (safety limit)
    permission_mode: str,         # "default", "acceptEdits", "plan", "bypassPermissions"
    allowed_tools: list[str],     # Which tools the agent can use
    cwd: str,                     # Working directory for tool execution
    hooks: dict,                  # PreToolUse/PostToolUse hooks (see Section 9)
    can_use_tool: callable,       # Permission callback function
)
```

Let us walk through each parameter:

| Parameter | Purpose | AI Doctor Value |
|-----------|---------|-----------------|
| `system_prompt` | Instructions that frame the agent's role | Clinical decision support prompt (60 lines) |
| `model` | Which Claude model to use | `settings.ai_model` → `"claude-opus-4-6"` |
| `output_format` | JSON Schema for structured responses | `PatientBriefing.model_json_schema()` |
| `max_turns` | Safety limit on agentic loop iterations | `2` (no tool use → only needs 1 turn + result) |
| `permission_mode` | How tool permissions are handled | `"bypassPermissions"` (backend automation) |
| `allowed_tools` | Whitelist of permitted tools | Not set in V1 (no tools needed) |
| `cwd` | Working directory for file/bash tools | Not set in V1 (no file operations) |
| `hooks` | Pre/post tool use callbacks | Not set in V1 (no observability yet) |

### Async Iteration Pattern

`query()` returns an async generator. You iterate with `async for`:

```python
async for message in query(prompt="...", options=options):
    if isinstance(message, AssistantMessage):
        # The model's text response or tool use requests
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)
            elif isinstance(block, ToolUseBlock):
                print(f"Tool call: {block.name}")

    elif isinstance(message, ResultMessage):
        # Final message — contains structured output, cost, duration
        if message.structured_output:
            data = message.structured_output  # dict matching your schema
        print(f"Cost: ${message.total_cost_usd:.4f}")
        print(f"Turns: {message.num_turns}")
```

The message types you will encounter:

| Type | When | Contains |
|------|------|----------|
| `AssistantMessage` | Each model response | `content` blocks: `TextBlock`, `ToolUseBlock`, `ThinkingBlock` |
| `UserMessage` | Tool results fed back | `content` blocks: `TextBlock`, `ToolResultBlock` |
| `SystemMessage` | System events | `subtype` and `data` fields |
| `ResultMessage` | Conversation complete | `structured_output`, `result`, `is_error`, `total_cost_usd`, `num_turns`, `duration_ms` |

### AI Doctor: Walking Through briefing_service.py

```
AI DOCTOR EXAMPLE:
Here is how the AI Doctor's briefing service (backend/src/services/briefing_service.py)
uses query(), annotated line by line:

  # 1. Build the options — everything the agent needs to know
  options = ClaudeAgentOptions(
      system_prompt=SYSTEM_PROMPT,      # 60-line clinical prompt (lines 25-63)
      model=settings.ai_model,          # From config.py: "claude-opus-4-6"
      output_format={                   # Structured output (Section 4)
          "type": "json_schema",
          "schema": PatientBriefing.model_json_schema(),
      },
      max_turns=2,                      # 1 turn for response + 1 safety margin
      permission_mode="bypassPermissions",  # No human approval needed
  )

  # 2. Send the patient JSON as the prompt and iterate
  result = None
  async for message in query(prompt=patient_json, options=options):

      # 3. Look for the final result
      if isinstance(message, ResultMessage):

          # 4. Happy path: validate structured output against Pydantic
          if not message.is_error and message.structured_output is not None:
              briefing = PatientBriefing.model_validate(message.structured_output)
              result = BriefingResponse(
                  **briefing.model_dump(),
                  generated_at=datetime.datetime.now(datetime.UTC),
              )

          # 5. Error path: agent reported an error
          if message.is_error:
              raise BriefingGenerationError(
                  code="AGENT_ERROR",
                  message=message.result or "Agent returned an error",
              )

Why max_turns=2?
  AI Doctor V1 has NO tools. The agent receives the full patient record in
  the prompt and responds with structured output. This needs exactly 1 turn.
  max_turns=2 provides a safety margin — if the model somehow requests a
  tool call, the loop will terminate after 2 iterations instead of running
  indefinitely.

Why patient_json as the prompt (not in messages)?
  query() accepts a single prompt string. The SDK places it as the user
  message. The system_prompt goes into the separate system field. This
  mirrors the raw API pattern from Doc 01: system is separate, user
  message is in the messages array.
```

### query() vs ClaudeSDKClient

The SDK offers two usage patterns:

| | `query()` | `ClaudeSDKClient` |
|-|-----------|-------------------|
| **Pattern** | One-shot, stateless | Multi-turn, stateful |
| **Lifecycle** | Single async generator | Context manager (`async with`) |
| **State** | No conversation memory | Maintains conversation across queries |
| **Use when** | Single prompt → result | Interactive/conversational agents |
| **AI Doctor** | Yes (one patient → one briefing) | Not used in V1 |

```python
# query() — stateless, one-shot (AI Doctor pattern)
async for message in query(prompt="Analyze this", options=options):
    ...

# ClaudeSDKClient — stateful, multi-turn
async with ClaudeSDKClient(options=options) as client:
    await client.query("First question")
    async for msg in client.receive_response():
        ...
    await client.query("Follow-up question")  # remembers context
    async for msg in client.receive_response():
        ...
```

AI Doctor uses `query()` because each briefing is independent — there is no conversation to maintain. The patient record goes in, the briefing comes out, done.

---

## 4. Structured Output

Structured output is how you get the model to return data in a predictable, validated format instead of free-form text. The SDK enforces this at the API level — the model is **constrained** to produce JSON matching your schema.

### The Flow: Pydantic → JSON Schema → API → Validated Response

```
┌─────────────────┐     model_json_schema()     ┌─────────────────┐
│  Pydantic Model │ ──────────────────────────>  │   JSON Schema   │
│  (schemas.py)   │                              │   (dict)        │
└─────────────────┘                              └────────┬────────┘
                                                          │
                                          output_format   │
                                          in options      │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  ClaudeAgent     │
                                                 │  Options         │
                                                 └────────┬────────┘
                                                          │
                                                  query() │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  Claude API      │
                                                 │  (constrained    │
                                                 │   generation)    │
                                                 └────────┬────────┘
                                                          │
                                          structured_output (dict)
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │  model_validate()│
                                                 │  → Pydantic obj  │
                                                 └─────────────────┘
```

### Step 1: Define the Pydantic Models

The schema is your contract. Every field, every type, every constraint.

```
AI DOCTOR EXAMPLE:
The AI Doctor's output schema lives in backend/src/models/schemas.py.
Three nested models compose into PatientBriefing:

  class Flag(BaseModel):
      category: Literal["labs", "medications", "screenings", "ai_insight"]
      severity: Literal["critical", "warning", "info"]
      title: str
      description: str
      source: Literal["ai"]        # Always "ai" in V1
      suggested_action: str | None = None

  class Summary(BaseModel):
      one_liner: str
      key_conditions: list[str]
      relevant_history: str

  class SuggestedAction(BaseModel):
      action: str
      reason: str
      priority: int

  class PatientBriefing(BaseModel):
      flags: list[Flag]
      summary: Summary
      suggested_actions: list[SuggestedAction]

Note the use of Literal types. The model CANNOT return severity: "high"
or category: "other" — the JSON Schema constrains generation to only the
enum values you define.
```

### Step 2: Convert to JSON Schema

Pydantic v2's `model_json_schema()` converts your model to a JSON Schema dict:

```python
schema = PatientBriefing.model_json_schema()
# Returns a dict like:
# {
#   "type": "object",
#   "properties": {
#     "flags": {"type": "array", "items": {"$ref": "#/$defs/Flag"}},
#     "summary": {"$ref": "#/$defs/Summary"},
#     "suggested_actions": {"type": "array", "items": {"$ref": "#/$defs/SuggestedAction"}}
#   },
#   "required": ["flags", "summary", "suggested_actions"],
#   "$defs": { ... }
# }
```

### Step 3: Pass to ClaudeAgentOptions

```python
options = ClaudeAgentOptions(
    output_format={
        "type": "json_schema",       # Tell the API to use JSON Schema mode
        "schema": schema,            # The schema dict from step 2
    },
    ...
)
```

The `output_format` dict tells the API: "constrain the model's output to valid JSON matching this schema." This is **not** the same as asking the model "please respond in JSON" in the system prompt — the API enforces it during token generation.

### Step 4: Validate the Response

The `ResultMessage.structured_output` field contains the parsed dict. You validate it with Pydantic:

```python
if isinstance(message, ResultMessage):
    if message.structured_output is not None:
        # structured_output is a dict — validate it into a typed object
        briefing = PatientBriefing.model_validate(message.structured_output)
        # Now briefing.flags[0].severity is a typed Literal, not a raw string
```

Why validate if the API already enforced the schema? Defense in depth. The API guarantees valid JSON structure, but `model_validate()` also runs Pydantic validators (custom validators, field constraints) and gives you a typed Python object instead of a raw dict.

### Common Pitfall: model_validate vs parse_obj

Pydantic v2 renamed `parse_obj()` to `model_validate()`. If you see `parse_obj` in older code, it is the v1 pattern:

```python
# WRONG (Pydantic v1 pattern)
briefing = PatientBriefing.parse_obj(data)

# RIGHT (Pydantic v2 pattern — what AI Doctor uses)
briefing = PatientBriefing.model_validate(data)
```

---

## 5. Error Handling

The SDK defines a hierarchy of exceptions that map to different failure modes in the CLI subprocess model. Each exception tells you **where** the failure occurred.

### Exception Hierarchy

```
┌────────────────────────────────────────────────────────────┐
│  Your Code calls query()                                   │
│                                                            │
│  What can go wrong?                                        │
│                                                            │
│  1. CLINotFoundError                                       │
│     └─ The Claude Code CLI binary is not installed         │
│        or not on PATH                                      │
│                                                            │
│  2. CLIConnectionError                                     │
│     └─ The CLI process started but communication           │
│        over stdin/stdout failed                            │
│                                                            │
│  3. ProcessError                                           │
│     └─ The CLI process crashed (non-zero exit code)        │
│                                                            │
│  4. CLIJSONDecodeError                                     │
│     └─ The CLI sent output that was not valid JSON         │
│                                                            │
│  5. ResultMessage.is_error = True                          │
│     └─ The conversation completed but the model            │
│        reported an error (not a Python exception)          │
└────────────────────────────────────────────────────────────┘
```

| Exception | Cause | Typical Resolution |
|-----------|-------|--------------------|
| `CLINotFoundError` | CLI binary missing | Install Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) |
| `CLIConnectionError` | Pipe communication failed | Check process resources, restart |
| `ProcessError` | CLI process crashed | Check CLI logs, API key validity |
| `CLIJSONDecodeError` | Malformed CLI output | SDK/CLI version mismatch, update both |
| `is_error=True` | Model-level error | Check prompt, schema, model availability |

### Wrapping SDK Errors in Domain Exceptions

A good practice is to catch SDK exceptions and re-raise them as your application's domain exceptions. This decouples your business logic from the SDK's error types.

```
AI DOCTOR EXAMPLE:
The briefing service (backend/src/services/briefing_service.py, lines 66-151)
wraps every SDK error into a BriefingGenerationError with a domain-specific
error code:

  class BriefingGenerationError(Exception):
      def __init__(self, code: str, message: str) -> None:
          self.code = code        # e.g., "CLI_NOT_FOUND", "PROCESS_ERROR"
          self.message = message   # Human-readable description

  # In generate_briefing():
  try:
      async for message in query(prompt=patient_json, options=options):
          ...
  except CLINotFoundError:
      raise BriefingGenerationError(
          code="CLI_NOT_FOUND",
          message="Claude Code CLI not found. Ensure it is installed.",
      )
  except CLIConnectionError as e:
      raise BriefingGenerationError(
          code="CLI_CONNECTION_ERROR",
          message=f"Failed to connect to Claude CLI: {e}",
      )
  except ProcessError as e:
      raise BriefingGenerationError(
          code="PROCESS_ERROR",
          message=f"Agent process failed: {e}",
      )
  except CLIJSONDecodeError as e:
      raise BriefingGenerationError(
          code="JSON_DECODE_ERROR",
          message=f"Failed to parse agent response: {e}",
      )

This pattern has three benefits:
  1. The router layer catches BriefingGenerationError, not SDK errors.
     Changing SDKs later does not change the router.
  2. Error codes ("CLI_NOT_FOUND") are stable strings for API consumers.
  3. The original exception is chained (via raise ... from) for debugging.

Note: BriefingGenerationError is re-raised early in the except chain to
avoid accidentally catching it in later except blocks.
```

---

## 6. Tool Creation (V2 Preview)

> **V1 Note:** The AI Doctor V1 does **not** use tools. This section previews V2 patterns for context. Skip to [Section 7 (Testing)](#7-testing-and-mocking) if you only need V1 knowledge.

In V2, agents will have tools — functions they can call to retrieve data, perform calculations, or interact with external systems. The SDK provides a decorator-based tool creation pattern.

### The @tool Decorator

```python
from claude_agent_sdk import tool

@tool("fetch_patient", "Retrieve a patient record by ID", {"patient_id": int})
async def fetch_patient(args: dict) -> dict:
    patient = await db.get_patient(args["patient_id"])
    return {
        "content": [{
            "type": "text",
            "text": json.dumps(patient.to_dict())
        }]
    }
```

The decorator registers three things:
1. **Name** (`"fetch_patient"`) — how the model refers to the tool
2. **Description** — helps the model decide when to use it (see Doc 02's [tool definitions](02-TOOL-USE-AND-AGENTIC-LOOP.md))
3. **Parameters schema** — JSON Schema for the tool's input

### MCP Server Registration

Tools are grouped into MCP servers (see Doc 04's [MCP protocol coverage](04-MCP-AND-A2A-PROTOCOLS.md)):

```python
from claude_agent_sdk import create_sdk_mcp_server

tools_server = create_sdk_mcp_server(
    name="briefing_tools",
    version="1.0.0",
    tools=[fetch_patient, check_lab_ranges, get_drug_interactions]
)
```

### Tool Naming Convention

When referencing tools in `allowed_tools`, use the MCP naming format:

```python
# Format: mcp__<server_name>__<tool_name>
options = ClaudeAgentOptions(
    allowed_tools=[
        "mcp__briefing_tools__fetch_patient",
        "mcp__briefing_tools__check_lab_ranges",
    ],
)
```

This naming convention connects to the MCP protocol from Doc 04 — each tool is namespaced by its server.

### Why V1 Has No Tools

```
AI DOCTOR EXAMPLE:
In V1, the briefing service sends the FULL patient record as the prompt:

  patient_json = _serialize_patient(patient)
  async for message in query(prompt=patient_json, options=options):
      ...

The agent receives everything it needs in one message. There is nothing
to "look up" — no reason to call a tool.

V2 will change this. Instead of sending the full record, the agent will
receive a patient_id and use tools to:
  - fetch_patient: Get demographics and conditions
  - check_lab_ranges: Compare labs against reference ranges
  - get_drug_interactions: Check medication combinations

This lets the agent reason about WHAT data it needs, not just analyze
what it is given. max_turns will increase from 2 to allow multiple
tool call rounds.
```

---

## 7. Testing and Mocking

**Golden rule: NEVER call a real LLM in unit tests.**

LLM calls are slow (~1-5 seconds), expensive (tokens cost money), and non-deterministic (same prompt can produce different output). Tests must be fast, free, and repeatable.

### Strategy: Mock at the SDK Boundary

Mock `query()` itself — not the HTTP client, not the CLI process. This gives you a clean seam between "SDK behavior" (mocked) and "your business logic" (tested).

```python
from unittest.mock import patch

@patch("src.services.briefing_service.query")
async def test_generate_briefing_success(mock_query, fake_patient):
    # Set up mock to return a fake ResultMessage
    msg = _make_result_message(structured_output=VALID_STRUCTURED_OUTPUT)
    mock_query.return_value = _async_iter([msg])

    # Call the real business logic
    result = await generate_briefing(fake_patient)

    # Assert on the business logic's output
    assert len(result.flags) == 1
    assert result.flags[0].title == "HbA1c elevated"
```

### Creating Fake ResultMessage Objects

The test needs objects that pass `isinstance(msg, ResultMessage)` checks. The pattern:

```python
def _make_result_message(*, structured_output=None, is_error=False, result=None):
    """Create a mock ResultMessage with the given fields."""
    msg = AsyncMock()
    msg.structured_output = structured_output
    msg.is_error = is_error
    msg.result = result
    # Make isinstance() work by setting the class
    msg.__class__ = ResultMessage
    return msg
```

The `msg.__class__ = ResultMessage` trick is critical — without it, `isinstance(msg, ResultMessage)` returns `False` and your business logic skips the mock.

### Async Generator Helper

`query()` returns an async generator, so your mock must too:

```python
async def _async_iter(items):
    """Async generator that yields each item."""
    for item in items:
        yield item

# Usage in test:
mock_query.return_value = _async_iter([msg])
```

### Testing Error Paths

```
AI DOCTOR EXAMPLE:
The test suite (backend/tests/test_briefing_service.py) tests four scenarios:

  1. Happy path: valid structured output → BriefingResponse
     mock_query returns a ResultMessage with structured_output=VALID_DICT
     Assert: result.flags[0].title == "HbA1c elevated"

  2. Agent error: model reports an error
     mock_query returns a ResultMessage with is_error=True
     Assert: raises BriefingGenerationError(code="AGENT_ERROR")

  3. No result: agent yields nothing
     mock_query returns an empty async iterator
     Assert: raises BriefingGenerationError(code="NO_RESULT")

  4. CLI not found: SDK throws CLINotFoundError
     mock_query.side_effect = CLINotFoundError()
     Assert: raises BriefingGenerationError(code="CLI_NOT_FOUND")

Each test verifies that the error wrapping from Section 5 works correctly —
SDK exceptions become domain exceptions with stable error codes.
```

### What NOT to Test

- Do not test that the SDK correctly calls the API. That is the SDK's job.
- Do not test that `model_json_schema()` produces correct JSON Schema. That is Pydantic's job.
- DO test your business logic: prompt construction, response validation, error wrapping, result transformation.

---

## 8. Permission Modes

The SDK's permission model controls what the agent can do without human approval. This maps directly to the CLI's permission system.

### Available Modes

```
┌───────────────────────────────────────────────────────────────────────┐
│                    PERMISSION MODES                                    │
│                                                                       │
│  "default"            Standard behavior. CLI prompts for              │
│                       tool permissions as configured.                  │
│                                                                       │
│  "acceptEdits"        Auto-accept file edits (Read, Write, Edit).    │
│                       Other tools still require approval.             │
│                       Use for: coding assistants, refactoring tools.  │
│                                                                       │
│  "plan"               Planning mode — the agent can read and         │
│                       analyze but NOT execute changes.                │
│                       Use for: code review, architecture analysis.    │
│                                                                       │
│  "bypassPermissions"  Skip ALL permission checks. The agent can      │
│                       use any allowed tool without approval.          │
│                       Use for: backend automation, CI/CD pipelines.   │
│                       ⚠ Use with caution — no human in the loop.     │
└───────────────────────────────────────────────────────────────────────┘
```

### When to Use Which

| Mode | Use Case | Risk Level |
|------|----------|------------|
| `default` | Interactive applications with a human watching | Low |
| `acceptEdits` | Coding assistants where file changes are expected | Medium |
| `plan` | Read-only analysis, code review, planning | Low |
| `bypassPermissions` | Backend services, automation, CI/CD | High (but controlled) |

### Combining with allowed_tools

Permission modes work alongside `allowed_tools` for defense in depth:

```python
# Read-only agent: can only search and read, no modifications
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep"],
    permission_mode="bypassPermissions",  # Safe because tools are read-only
)

# Full-power agent with human oversight
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Bash"],
    permission_mode="default",  # Human approves each tool use
)
```

```
AI DOCTOR EXAMPLE:
The briefing service uses bypassPermissions because:

  1. It runs as a backend service — no human is watching each request.
  2. V1 has NO tools — the agent only produces structured output.
     There is nothing to "permit" or "deny."
  3. max_turns=2 limits the blast radius even if the model tried
     to use a tool unexpectedly.

  options = ClaudeAgentOptions(
      permission_mode="bypassPermissions",
      max_turns=2,
  )

In V2, when tools are added, this will likely change to a more
restrictive mode — or use allowed_tools to whitelist only the
specific tools the briefing agent needs.
```

---

## 9. Hooks and Observability (V2 Preview)

> **V1 Note:** The AI Doctor V1 does **not** use hooks or observability. This section previews V2 patterns. Skip to [Section 10 (Summary)](#10-summary) if you only need V1 knowledge.

Hooks let you intercept tool use before and after execution. They are the SDK's extension point for security, logging, and observability.

### Hook Types

| Hook | When It Fires | Use Case |
|------|---------------|----------|
| `PreToolUse` | Before a tool executes | Validation, blocking dangerous commands, logging |
| `PostToolUse` | After a tool completes | Logging results, metrics, audit trail |

### HookMatcher Pattern

Hooks are registered with matchers that filter which tools they apply to:

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

async def validate_bash(input_data, tool_use_id, context):
    """Block dangerous bash commands."""
    if input_data["tool_name"] == "Bash":
        command = input_data["tool_input"].get("command", "")
        if "rm -rf" in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Dangerous command blocked",
                }
            }
    return {}

async def log_tool_use(input_data, tool_use_id, context):
    """Log all tool invocations for audit."""
    print(f"Tool: {input_data.get('tool_name')}")
    return {}

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[validate_bash]),  # Only Bash
            HookMatcher(hooks=[log_tool_use]),                    # All tools
        ],
        "PostToolUse": [
            HookMatcher(hooks=[log_tool_use]),
        ],
    }
)
```

The `matcher` field filters by tool name. Omitting it matches all tools.

### Langfuse Integration Pattern (V2)

For production observability, hooks can forward data to Langfuse:

```python
from langfuse import Langfuse

langfuse = Langfuse()

async def langfuse_hook(input_data, tool_use_id, context):
    langfuse.trace(
        name=f"tool:{input_data.get('tool_name')}",
        input=input_data.get("tool_input"),
    )
    return {}
```

### Why V1 Skips Observability

V1 has no tools, so there are no tool calls to observe. The complexity budget for V1 is focused on getting the core briefing pipeline working correctly. Observability (Langfuse traces, hook-based logging) is planned for V2 when tools introduce more moving parts to monitor.

---

## 10. Summary

### The SDK as the Right Level of Abstraction

The Claude Agent SDK occupies a sweet spot for single-provider applications like AI Doctor:

- **More than the raw API**: You do not write the agentic loop, tool dispatch, or permission checks.
- **Less than a framework**: No multi-provider abstraction, no chain system, no memory backends. Fewer moving parts = easier debugging.
- **Close to the metal**: The SDK's concepts (messages, tools, schemas) map directly to API concepts. Understanding the SDK means understanding the API.

### What Doc 02 Covered vs What This Doc Covered

| Topic | Doc 02 | Doc 07 (this doc) |
|-------|--------|-------------------|
| Framework comparison (SDK vs LangChain vs raw API) | Detailed table + decision tree | Reference only |
| SDK architecture (subprocess model, message flow) | Not covered | Full treatment |
| `query()` internals and parameters | Brief code example | Parameter-by-parameter walkthrough |
| Structured output flow | Mentioned | End-to-end: Pydantic → JSON Schema → API → validate |
| Error handling | Not covered | Full exception hierarchy + wrapping pattern |
| Tool creation | Not covered | `@tool` decorator + MCP registration (V2) |
| Testing patterns | Not covered | Mock strategy + async generator helpers |
| Permission modes | Listed | When-to-use guide + defense-in-depth |
| Hooks | Not covered | PreToolUse/PostToolUse + Langfuse pattern |

### Checklist: What You Should Be Able to Explain

After reading this document, you should be able to explain:

- [ ] Why the SDK spawns a CLI subprocess instead of calling the API directly
- [ ] What `query()` returns and how to iterate over it
- [ ] The four steps of structured output: Pydantic model → JSON Schema → API constraint → model_validate()
- [ ] The five error types and where each failure occurs in the subprocess chain
- [ ] Why you mock `query()` (not the HTTP client) in tests
- [ ] The difference between `bypassPermissions` and `acceptEdits`
- [ ] Why AI Doctor V1 uses `max_turns=2` with `bypassPermissions` and no tools
- [ ] How hooks intercept tool execution and why V1 does not use them

---

**Previous**: [06 — Training & Running Models](06-TRAINING-AND-RUNNING-MODELS.md)
**Series Overview**: [00 — Overview](00-OVERVIEW.md)
