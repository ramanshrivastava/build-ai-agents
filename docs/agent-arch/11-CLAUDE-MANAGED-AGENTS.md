# Claude Managed Agents

**Part 11: Agent Architecture & AI Model Internals Series**
**Module 4.2 — Autonomous Agents: the managed-runtime path** (Module 4.1, building the harness yourself, is [10-CLAUDE-AGENT-SDK.md](10-CLAUDE-AGENT-SDK.md))
**AI Doctor Assistant Project**

---

## Learning Objectives

After reading this document, you will understand:

- How Claude Managed Agents differ from the Claude Agent SDK used by the main AI Doctor backend
- How the same clinical briefing agent can run through two runtimes with the same app-level API shape
- How Managed Agents custom tools work through `agent.custom_tool_use` and `user.custom_tool_result` events
- The **inversion of control** that defines the managed runtime: your backend stops hosting the loop and becomes a tool server
- Why this repo reuses a Managed Agents session per synthetic patient, while still sending the latest patient JSON every run
- What changes when deployment responsibility moves from your FastAPI process to Anthropic's managed runtime
- The failure modes people hit on their *second* request, not their first — and how the live code defends against each one

This lesson uses synthetic patient data only. Do not send real PHI through this course example.

---

## 1. Two Ways to Run the Same Agent

The repo now demonstrates the same AI Doctor briefing through two paths:

| Path | Endpoint | Runtime | Tool bridge |
|------|----------|---------|-------------|
| Build the harness yourself | `POST /api/v1/patients/{id}/briefing` | Claude Agent SDK subprocess from FastAPI | In-process SDK MCP server |
| Use a managed runtime | `POST /api/v1/patients/{id}/briefing/managed` | Claude Managed Agents session | Managed Agents custom tool events |

The output stays the same:

```python
class BriefingResponse(PatientBriefing):
    generated_at: datetime.datetime
```

The frontend can display either result because both paths validate into the same `PatientBriefing` schema.

---

## 2. Agent SDK Runtime

The existing SDK path is owned by your backend process:

```text
FastAPI request
  -> briefing_service.generate_briefing()
  -> agents/briefing_agent.py
  -> claude_agent_sdk.query()
  -> Claude Code CLI subprocess
  -> in-process MCP server
  -> search_clinical_guidelines()
  -> Qdrant + embeddings
```

You control the whole harness:

- Prompt construction
- `ClaudeAgentOptions`
- MCP server registration
- Tool allowlist
- Structured output schema
- CLI subprocess lifecycle
- Error handling around SDK shutdown

This is the best path when you want local control and can own the process runtime.

---

## 3. Managed Agents Runtime

The managed path moves the agent session into Anthropic's beta Managed Agents API:

```text
FastAPI request
  -> managed_briefing_service.generate_managed_briefing()
  -> get/create Managed Agents session for patient
  -> send user.message with latest synthetic patient JSON
  -> poll/list session events
  -> handle agent.custom_tool_use
  -> send user.custom_tool_result
  -> validate final agent.message JSON
```

The important shift is that the session is now a remote resource. Your app still owns patient data, Qdrant, and the clinical search tool implementation, but Anthropic owns the agent session loop and environment.

### Why reuse a session per patient?

This course intentionally reuses one Managed Agents session per synthetic patient so learners can see session persistence. The backend still sends the full latest patient JSON on every run and the system prompt tells the agent to treat that JSON as the source of truth.

That avoids the main risk of persistent sessions: stale memory silently overriding current application state.

---

## 4. Custom Tool Event Flow

### The mental model: inversion of control

This is the single most important idea in this document. With the Agent SDK,
**you host the loop and Claude calls into your in-process tools**. With Managed
Agents, **Anthropic hosts the loop and your backend becomes the tool server** —
a service that watches for tool-use events, executes them, and posts results
back.

| | Agent SDK (Module 4.1) | Managed Agents (Module 4.2) |
|---|---|---|
| Who runs the agentic loop | Your process | Anthropic's runtime |
| Who calls whom for tools | The loop calls your Python function directly | You poll for `agent.custom_tool_use` events and answer them |
| Your app's role | Orchestrator | Tool server + result validator |

Once you see the runtimes this way, every design choice in
`managed_briefing_service.py` follows from it: the polling loop, the event
deduplication, the bounded rounds, the schema validation at the boundary. If
you carry the SDK mental model ("I call the agent, it returns") into the
managed runtime, you will write code that hangs, replays old tool calls, or
trusts unvalidated output. Section 7 catalogs those traps one by one.

The SDK path exposes tools through `create_sdk_mcp_server()`. Managed Agents custom tools work differently:

```text
Agent needs a guideline
  -> emits agent.custom_tool_use
  -> session goes idle and waits
  -> FastAPI executes search_clinical_guidelines locally
  -> FastAPI sends user.custom_tool_result
  -> managed session resumes
```

The managed agent is configured with this custom tool schema:

```json
{
  "type": "custom",
  "name": "search_clinical_guidelines",
  "description": "Search clinical guidelines, drug interactions, and protocols.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string" },
      "specialty": { "type": "string" },
      "max_results": { "type": "integer" }
    },
    "required": ["query"]
  }
}
```

The tool implementation is not duplicated. The managed service calls the existing handler from `src.agents.tools.search_clinical_guidelines`, then posts the text result back to the managed session.

---

## 5. Setup

Managed Agents requires beta API access and an API key:

```bash
cd backend
cp .env.example .env
# Set ANTHROPIC_API_KEY first.
uv run python ../scripts/setup_managed_agent.py
```

The setup script:

1. Creates any missing local SQLAlchemy tables for the course database.
2. Creates a Claude Managed Agents cloud environment.
3. Creates an AI Doctor managed agent with the clinical search custom tool.
4. Prints the `.env` values:

```bash
MANAGED_AGENT_ID=...
MANAGED_ENVIRONMENT_ID=...
```

Then run the app as usual:

```bash
cd backend
uv run uvicorn src.main:app --reload
```

Generate through the managed runtime:

```bash
curl -X POST http://localhost:8000/api/v1/patients/1/briefing/managed
```

Reset one patient's managed session:

```bash
curl -X DELETE http://localhost:8000/api/v1/patients/1/briefing/managed/session
```

---

## 6. Deployment Comparison

The FastAPI deployment shape stays mostly the same. You still deploy:

- Backend
- Frontend
- PostgreSQL
- Qdrant
- Secrets for API keys and database URLs

What changes is runtime ownership:

| Concern | Agent SDK path | Managed Agents path |
|---------|----------------|---------------------|
| Agent loop | Your backend subprocess | Anthropic Managed Agents session |
| Tool execution | In-process SDK MCP server | Your backend handles custom-tool events |
| Session state | Per request unless you store it | Remote session, mapped to patient in Postgres |
| Local dependency | Claude Agent SDK / Claude Code CLI | Anthropic Python SDK |
| Failure mode | CLI/subprocess errors | Remote session/API/event errors |

For this repo, deployment does not need a separate worker. The `/briefing/managed` request handles tool events inline. A production system with long-running managed sessions would usually move tool dispatch into a worker.

---

## 7. What People Miss

Everything below is verified against the live implementation in
[`managed_briefing_service.py`](../../backend/src/services/managed_briefing_service.py)
and its [tests](../../backend/tests/test_managed_briefing_service.py). These
are the traps that don't show up in a hello-world demo — most of them bite on
the *second* request, the *slow* tool call, or the *malformed* response.

### 7.1 The event list is a history, not a queue

> [!WARNING]
> **Reality check (event-replay) —** Listing session events returns the session's *entire append-only history*, not just what's new. On a reused session, a naive poll loop will happily re-handle last week's `agent.custom_tool_use` events — re-running tools and re-posting results into a conversation that already moved on. This is invisible on request one and guaranteed on request two. The live code defends twice: `_list_event_ids()` snapshots every pre-existing event ID *before* sending the new patient message, and `_wait_for_briefing_json()` keeps a per-run `handled_tool_ids` set so no tool event is dispatched twice. But the snapshot creates its own trap: history can contain *obligations*, not just facts. If a previous run died after the agent emitted a tool call but before the result was sent, marking that event "seen" would leave the session blocked forever — so the snapshot pass also answers any unanswered tool call with `is_error=True` before sending the new message. If you build on Managed Agents and skip this, you have written a replay bug *and* a deadlock, not an agent.

### 7.2 Session memory is a cache, not a source of truth

> [!WARNING]
> **Reality check (session-memory) —** Persistent sessions are the headline feature of the managed runtime — and the easiest way to serve stale state. If the patient record changes between runs, the session still "remembers" the old one. This repo's rule: **resend the authoritative state on every run, and tell the agent to prefer it.** `_patient_prompt()` sends the full latest patient JSON each time, and `MANAGED_SYSTEM_PROMPT` explicitly instructs the agent to treat that JSON as the source of truth "even when the session contains older messages for the same patient." Treat session memory as a conversation cache; your database remains the system of record.

### 7.3 There is no structured-output guarantee — validate at the boundary

> [!WARNING]
> **Reality check (output-validation) —** The SDK path can lean on `output_format` for schema-shaped output. This managed implementation gets text back and must defend itself: `_extract_json()` strips markdown fences (note the irony — the system prompt says "Do not wrap the JSON in Markdown" *and* the code still handles fenced output, because prompts are requests, not contracts), then `PatientBriefing.model_validate()` is the real gate. Failures map to a typed `MANAGED_AGENTS_INVALID_OUTPUT` error instead of leaking garbage to the frontend. Whatever runtime you use: the model's output crosses into your application only through a schema validator.

### 7.4 Bound every loop that waits on a remote session

> [!WARNING]
> **Reality check (unbounded-loops) —** An event loop polling a remote session has two ways to run forever: the session never goes idle, or the agent keeps calling tools. The live code bounds both — a wall-clock deadline (`managed_agent_session_timeout_seconds`, default 240s) and a tool-round ceiling (`managed_agent_max_tool_rounds`, default 16) — and converts each into a typed `MANAGED_AGENTS_TIMEOUT` error. It also handles `session.error` events explicitly. And bailing out has its own hygiene: raising while a tool call is unanswered would wedge the session, so the code answers the over-budget call with an error result and sends `user.interrupt` before raising — the abandoned session is left idle, not waiting forever on a result that will never come. "It worked in the demo" is not evidence your loop terminates; the bounds are what make this production-shaped code instead of a hope.

### 7.5 Tool latency is polling-bound, and every tool call must be answered

> [!WARNING]
> **Reality check (tool-dispatch) —** Two sub-traps here. First, latency: when the agent calls a tool, the remote session goes idle and waits for *you*; with a poll-and-sleep loop (this service sleeps 0.5s between empty polls), tool round-trip time is set by your polling cadence, not your function's speed. Second, completeness: every `agent.custom_tool_use` must get a `user.custom_tool_result` — including ones you don't recognize. `_handle_custom_tool()` answers unknown tool names with `is_error=True` instead of ignoring them, because an unanswered tool call leaves the session waiting and your request running into its deadline. This repo handles dispatch inline for teaching clarity; a production system with long-running sessions would move it to a worker.

### 7.6 Remote sessions are resources you must track and clean up

> [!WARNING]
> **Reality check (remote-resources) —** Every session you create lives on Anthropic's side until deleted. If you don't persist the mapping, you'll either orphan sessions or lose the persistence benefit by creating a new one per request. This repo stores the mapping in Postgres (`ManagedAgentSession`: one row per patient, unique `session_id`, `last_used_at`) and exposes an explicit reset path — `DELETE /patients/{id}/briefing/managed/session` — which best-effort deletes the remote session and always removes the local row. Sessions are infrastructure: give them a table, a lifecycle, and a delete button.

### 7.7 It's a beta surface — pin it, wrap it, mock it

> [!WARNING]
> **Reality check (beta-surface) —** Everything here lives under `client.beta.*` (`beta.sessions`, `beta.sessions.events`). Beta surfaces move. Three defenses in this repo: the `anthropic` dependency is version-pinned (`>=0.104.1`), every API error (`APIConnectionError`, `APITimeoutError`, `APIError`) is wrapped into the app's own `BriefingGenerationError` codes so the frontend never sees raw SDK exceptions, and tests mock at the client boundary — `AsyncAnthropic` is replaced with `SimpleNamespace` fakes whose `_AsyncEvents` batches simulate successive polling rounds. No test calls the real API; the whole event protocol is exercised against fakes. When (not if) the beta changes, the blast radius is one service module and one test file.

---

## 8. When to Choose Which

An opinionated take, in line with how this course is built:

**Default to the Agent SDK (Module 4.1).** It is the simplest local development
loop, your tools stay in-process Python functions, errors are process errors
you can see, and nothing about your agent lives behind a beta API. If you are
learning how agent harnesses work — the point of this course — owning the loop
is the better teacher.

**Reach for Managed Agents (Module 4.2) when sessions are the product.** If you
want persistent, resumable agent sessions as a first-class API concept, want
Anthropic operating the loop's runtime, and accept integrating against a beta
event surface (with the defenses from Section 7), the managed path removes the
harness from your operational plate — while *adding* the tool-server and
session-lifecycle responsibilities this document covers.

The wrong reason to choose Managed Agents: assuming "managed" means less code.
As Section 7 shows, you trade harness code for boundary code — polling,
deduplication, validation, lifecycle. It's different work, not less work.

In both cases, the application boundary should stay stable: validate model output into your own schema before returning it to the frontend.

---

## References

- Anthropic Python SDK Managed Agents beta API: `client.beta.agents`, `client.beta.environments`, `client.beta.sessions`, and `client.beta.sessions.events`
- Claude Agent SDK Python custom tools: `@tool`, `create_sdk_mcp_server()`, `ClaudeAgentOptions`
- Live repo implementation: `backend/src/services/managed_briefing_service.py`
- Live repo tests (client-boundary mocking pattern): `backend/tests/test_managed_briefing_service.py`
