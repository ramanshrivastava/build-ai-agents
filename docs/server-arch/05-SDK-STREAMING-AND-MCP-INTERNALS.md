# SDK Streaming and MCP Internals

**Part 5 of 5: Async Server Architecture Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [The Architecture: SDK to CLI Subprocess](#1-the-architecture-sdk-to-cli-subprocess)
3. [String vs Streaming Prompts: The Critical Fork](#2-string-vs-streaming-prompts-the-critical-fork)
4. [Why String Prompts Break MCP Tools](#3-why-string-prompts-break-mcp-tools)
5. [MCP Server Bridge: How create_sdk_mcp_server Works](#4-mcp-server-bridge-how-create_sdk_mcp_server-works)
6. [The Shutdown Race: BaseExceptionGroup with CLIConnectionError](#5-the-shutdown-race-baseexceptiongroup-with-cliconnectionerror)
7. [Complete Message Flow: RAG Agent with Tools](#6-complete-message-flow-rag-agent-with-tools)
8. [Summary](#7-summary)

---

## Learning Objectives

After reading this document, you will understand:

- How the Claude Agent SDK **communicates with the CLI subprocess** via stdin/stdout JSONL
- Why **string prompts silently break MCP tools** and how streaming prompts fix this
- How `create_sdk_mcp_server()` **bridges JSONRPC messages** between the CLI and your Python tools
- Why `BaseExceptionGroup` wrapping `CLIConnectionError` appears during **shutdown** and when it's safe to ignore
- The **complete message flow** of a RAG agent request with tool calls

Key mental models to internalize:

- The SDK is a **JSONL bridge between your Python app and a Claude Code CLI subprocess**. It does not call the Claude API directly.
- String prompts close stdin immediately. MCP tool communication flows through stdin. **These two facts are incompatible** — streaming prompts are mandatory when tools are present.
- During shutdown, task group cancellation can race with in-flight control request handlers. **If you have a result, the race is harmless.**

Common misconceptions to avoid:

- "The SDK calls the Claude API directly" — No. It spawns a CLI subprocess and communicates over stdin/stdout.
- "String prompts are simpler and work fine" — They work for toolless agents. They silently break MCP tool communication.
- "`BaseExceptionGroup` means something is wrong" — Not necessarily. During shutdown it's often a harmless race condition.

---

## 1. The Architecture: SDK to CLI Subprocess

The Agent SDK doesn't call the Claude API directly. It spawns a **Claude Code CLI subprocess** and communicates over **stdin/stdout using JSONL and a control protocol**.

```
Python App                    SDK                         CLI Subprocess
─────────                    ───                         ──────────────
query(prompt, options) ──→ InternalClient
                           ├─ SubprocessCLITransport ──→ claude --input-format stream-json
                           │   stdin  ──────────────►   (messages in)
                           │   stdout ◄──────────────   (messages out)
                           └─ Query handler
                              ├─ message reader
                              ├─ control request router
                              └─ MCP server bridge
```

**Key files in SDK** (`.venv/lib/python3.13/site-packages/claude_agent_sdk/`):

| File | Role |
|------|------|
| `query.py` | Entry point — the `query()` async generator |
| `_internal/client.py` | Orchestration — `InternalClient.process_query()` |
| `_internal/query.py` | Control protocol, MCP routing, task group management |
| `_internal/transport/subprocess_cli.py` | Process spawning, stdin/stdout streams |
| `_internal/message_parser.py` | JSON to typed Message objects |

The transport layer is always in streaming mode internally (`_is_streaming = True`). The distinction between string and streaming prompts is handled one level up, in `InternalClient.process_query()`.

---

## 2. String vs Streaming Prompts: The Critical Fork

When `query()` is called, `InternalClient.process_query()` checks `isinstance(prompt, str)` and takes one of two paths.

### String prompt path (`prompt="patient data..."`)

```python
# _internal/client.py:122-134
if isinstance(prompt, str):
    user_message = {
        "type": "user",
        "session_id": "",
        "message": {"role": "user", "content": prompt},
        "parent_tool_use_id": None,
    }
    await chosen_transport.write(json.dumps(user_message) + "\n")
    await chosen_transport.end_input()  # ← CLOSES STDIN IMMEDIATELY
```

The client writes the prompt as a single JSONL message, then calls `end_input()` which closes stdin via `aclose()`. One-shot: CLI reads prompt, reasons, outputs result. **No further communication possible over stdin.**

### Async iterator path (`prompt=async_generator()`)

```python
# _internal/client.py:135-137
elif isinstance(prompt, AsyncIterable) and query._tg:
    query._tg.start_soon(query.stream_input, prompt)  # ← BACKGROUND TASK
```

The `stream_input()` method runs as a background task inside the query's `anyio` task group. It writes each message from the iterator, then — critically — **waits before closing stdin**:

```python
# _internal/query.py:570-600
async def stream_input(self, stream):
    async for message in stream:
        if self._closed:
            break
        await self.transport.write(json.dumps(message) + "\n")

    # If tools or hooks need bidirectional communication,
    # wait for the first result before closing stdin
    if self.sdk_mcp_servers or has_hooks:
        with anyio.move_on_after(self._stream_close_timeout):
            await self._first_result_event.wait()  # ← KEEPS STDIN ALIVE

    await self.transport.end_input()  # ← Only closes after result received
```

The `_first_result_event` is an `anyio.Event` set when the message reader encounters a `ResultMessage`. This ensures stdin stays open for the entire agent turn — including all MCP tool calls — and only closes after the agent has produced its final output.

---

## 3. Why String Prompts Break MCP Tools

Two message flows share the stdin/stdout channels:

### Regular messages (app to CLI via stdin, CLI to app via stdout)

```
stdin:  {"type": "user", "message": {"role": "user", "content": "..."}}
stdout: {"type": "assistant", ...}  →  {"type": "result", ...}
```

### Control protocol (CLI to SDK to CLI, bidirectional over stdin)

```
stdout: {"type": "control_request", "request_id": "req_1", "request": {
           "subtype": "mcp_message", "server_name": "briefing",
           "message": {"jsonrpc": "2.0", "method": "tools/call", "params": {...}}
         }}

stdin:  {"type": "control_response", "response": {
           "subtype": "success", "request_id": "req_1",
           "response": {"mcp_response": {...}}
         }}
```

When the agent decides to call a tool, the CLI sends a `control_request` on stdout. The SDK executes the tool in-process, then writes a `control_response` back on stdin. **This requires stdin to be open.**

### The failure mode with string prompts

1. CLI starts, reads the user message from stdin
2. SDK calls `end_input()` — **stdin is now closed**
3. Agent decides to call `search_clinical_guidelines`
4. CLI sends `control_request` on stdout
5. SDK receives it, executes the tool, tries to write `control_response` back on stdin
6. **stdin is closed** — tool response never reaches CLI — **silent failure**

The agent either hallucinates a tool result or gives up on tool use entirely. No error is raised.

### The fix — `_as_stream()` in `briefing_agent.py:201-208`

```python
async def _as_stream(text: str) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "user", "message": {"role": "user", "content": text}}
```

Wrapping the prompt as a single-element async iterator flips the SDK into the streaming code path. The `stream_input()` background task writes the message, detects MCP servers in the options, and waits for `_first_result_event` before closing stdin.

```
AI DOCTOR EXAMPLE:
In briefing_agent.py, the patient JSON is passed through _as_stream()
before reaching query(). This keeps stdin open so the agent can call
search_clinical_guidelines (via the "briefing" MCP server) multiple
times during its 4-turn reasoning loop. Without this wrapper, the
tool calls silently fail and the briefing lacks evidence citations.
```

---

## 4. MCP Server Bridge: How `create_sdk_mcp_server()` Works

```python
briefing_tools = create_sdk_mcp_server(
    name="briefing", version="1.0.0",
    tools=[search_clinical_guidelines],
)
```

This creates an **in-process MCP server** — not a separate subprocess. The SDK manually bridges JSONRPC messages between the CLI subprocess and the Python MCP server:

```
CLI subprocess                SDK Query handler              In-process MCP server
──────────────                ─────────────────              ─────────────────────
Agent calls tool ──stdout──→ _handle_control_request()
                              ├─ parse control_request
                              ├─ extract subtype: "mcp_message"
                              ├─ route by JSONRPC method:
                              │   "initialize"  → handshake
                              │   "tools/list"  → server.list_tools()
                              │   "tools/call"  → server.call_tool()  ──→ search_clinical_guidelines()
                              │                                          ├─ embed query
                              │                                          ├─ search Qdrant
                              │                                          └─ return XML sources
                              ├─ wrap response as control_response
                              └─ write to stdin ──stdin──→ Agent receives tool result
```

The routing happens in `_internal/query.py`. When a `control_request` arrives with `subtype: "mcp_message"`, the query handler calls `_handle_sdk_mcp_request()` which manually dispatches based on the JSONRPC method:

| JSONRPC Method | SDK Handler | What it does |
|----------------|-------------|--------------|
| `initialize` | Handshake response | Returns protocol version and capabilities |
| `notifications/initialized` | No-op | Acknowledges initialization |
| `tools/list` | `server.list_tools()` | Returns tool names, descriptions, input schemas |
| `tools/call` | `server.call_tool()` | Executes the Python function, returns result |

**Why manual routing?** The Python MCP SDK lacks a Transport abstraction for in-process communication (the TypeScript SDK has one). So the Agent SDK manually maps JSONRPC methods to MCP server request handlers, serializing and deserializing at each boundary.

Each control request is handled in a separate `anyio` task via `self._tg.start_soon()`. This means multiple tool calls can be in-flight concurrently within the same agent turn, though in practice the CLI sends them sequentially.

---

## 5. The Shutdown Race: `BaseExceptionGroup` with `CLIConnectionError`

### What happens during normal shutdown

After the message reader yields the final `ResultMessage`, `InternalClient.process_query()` enters its `finally` block and calls `query.close()`:

```python
# _internal/query.py:615-623
async def close(self):
    self._closed = True
    if self._tg:
        self._tg.cancel_scope.cancel()     # Cancel all background tasks
        with suppress(anyio.get_cancelled_exc_class()):
            await self._tg.__aexit__(...)   # Wait for cleanup
    await self.transport.close()            # Close subprocess
```

### The race condition

The query handler uses an `anyio` task group with concurrent tasks:

- **Task A:** Message reader (reading stdout, dispatching to message channel)
- **Task B:** Control request handler (routing MCP messages, writing stdin)
- **Task C:** Stream input writer (writing user messages to stdin)

When `close()` cancels the task group:

1. Cancel scope fires on all tasks
2. **Task B** is mid-flight handling a late control request (e.g., the CLI sent one just before producing the result)
3. Task B tries to write the response via `transport.write()`
4. Transport is already closing — raises `CLIConnectionError`
5. `anyio` collects the exception into a `BaseExceptionGroup`

This bubbles up through `process_query()` to the caller's `async for` loop.

### The defensive pattern (`briefing_agent.py:289-305`)

```python
except BaseExceptionGroup as eg:
    cli_errors = eg.subgroup(CLIConnectionError)
    if cli_errors and result is not None:
        # Already have our briefing — shutdown noise, ignore
        logger.warning("CLIConnectionError after result (ignoring)")
    elif cli_errors:
        # No result yet — this is a real failure
        raise BriefingGenerationError(code="CLI_CONNECTION_ERROR", ...)
    else:
        # Not a CLI error — something else went wrong
        raise
```

**Rule of thumb:** If you have a valid `ResultMessage`, any `CLIConnectionError` during shutdown is safe to ignore. If you don't have a result, it's a real error — the connection dropped before the agent finished.

The same logic also handles bare `CLIConnectionError` (not wrapped in an exception group) at `briefing_agent.py:281-288`, since the exception can arrive either way depending on timing.

---

## 6. Complete Message Flow: RAG Agent with Tools

Putting it all together, here is the full message flow for a RAG briefing request:

```
 1. App calls query(prompt=_as_stream(patient_json), options)
 2. SDK spawns CLI with --input-format stream-json
 3. SDK writes {"type":"user","message":{"role":"user","content":"...patient..."}} to stdin
 4. stream_input() detects MCP servers → waits for _first_result_event (stdin stays open)

 5. CLI agent reads patient record, reasons about conditions
 6. CLI agent decides to search → sends control_request on stdout
    (method: "tools/call", tool: "mcp__briefing__search_clinical_guidelines")

 7. SDK routes control_request → _handle_sdk_mcp_request()
    → calls search_clinical_guidelines(query="metformin renal dosing eGFR 45")
    → embeds query → searches Qdrant → returns XML source chunks

 8. SDK writes control_response on stdin → CLI receives tool result
 9. CLI agent may search again (up to max_turns=4)

10. CLI agent generates final briefing with citations
11. CLI outputs ResultMessage with structured_output matching PatientBriefing schema
12. _first_result_event.set() → stream_input() calls end_input() → stdin closes

13. SDK yields ResultMessage → app validates as PatientBriefing via model_validate()
14. query.close() → task group cancels → possible CLIConnectionError (ignored if result exists)
```

Steps 6-8 may repeat multiple times as the agent searches for different conditions (e.g., diabetes management, then drug interactions, then screening guidelines).

```
AI DOCTOR EXAMPLE:
For a patient with diabetes and hypertension on metformin + lisinopril,
the agent typically makes 2-3 tool calls: one for diabetes management
guidelines, one for ACE inhibitor + metformin interactions, and possibly
one for cardiovascular screening. Each tool call follows the full
control_request → execute → control_response cycle described above.
The entire multi-turn flow completes in a single query() call.
```

---

## 7. Summary

| Concept | Key Takeaway |
|---------|--------------|
| SDK architecture | Spawns CLI subprocess, communicates via stdin/stdout JSONL |
| String prompts | Close stdin immediately after writing — breaks MCP tools |
| Streaming prompts | Keep stdin open via `_first_result_event` — required for tools |
| `_as_stream()` | Wraps string as async iterator to force streaming path |
| MCP bridge | In-process server, manually routed JSONRPC over control protocol |
| Shutdown race | Task group cancellation can race with in-flight control handlers |
| `BaseExceptionGroup` | Safe to ignore if you already have a `ResultMessage` |

### What to remember when building agents with tools

1. **Always use an async iterator prompt** when your agent has MCP tools or hooks. The `_as_stream()` pattern is the minimal wrapper.
2. **Handle `BaseExceptionGroup`** around `query()`. Check for `CLIConnectionError` via `.subgroup()` and decide based on whether you have a result.
3. **The control protocol is bidirectional over stdin.** Anything that closes stdin early — string prompts, premature `end_input()`, process signals — will silently break tool communication.

### Cross-references

- **`briefing_agent.py:201-208`** — The `_as_stream()` implementation
- **`briefing_agent.py:289-305`** — The `BaseExceptionGroup` handler
- **`04-ASYNC-PATTERNS-FOR-RAG.md`** — Async patterns for the RAG pipeline that feeds into this agent
- **`../RAG-ARCH.md`** — Full RAG architecture including Qdrant, embeddings, and tool definitions

---

**Previous**: `04-ASYNC-PATTERNS-FOR-RAG.md` — Async patterns for RAG pipelines
