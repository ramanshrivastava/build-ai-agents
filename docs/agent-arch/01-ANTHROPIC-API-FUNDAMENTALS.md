# Anthropic API Fundamentals

**Part 1 of 8: Agent Architecture & AI Model Internals Series**
**AI Doctor Assistant Project**

---

## Table of Contents

1. [Learning Objectives](#learning-objectives)
2. [The API Contract -- Stateless Request/Response](#1-the-api-contract----stateless-requestresponse)
3. [Authentication](#2-authentication)
4. [Making Your First Request](#3-making-your-first-request)
5. [The Messages Array](#4-the-messages-array)
6. [Response Structure](#5-response-structure)
7. [Model Selection](#6-model-selection)
8. [Configuration Parameters](#7-configuration-parameters)
9. [Streaming (SSE)](#8-streaming-sse)
10. [Summary](#9-summary)

---

## Learning Objectives

After reading this document, you will understand:

- Why the Anthropic API is **stateless** and what that means for how you build applications
- How to **authenticate** API requests and manage keys securely
- The **anatomy** of a Messages API request and response, field by field
- How the **messages array** works as the conversation's memory
- The **differences** between Claude Opus, Sonnet, and Haiku and when to use each
- What every **configuration parameter** does (temperature, top_p, top_k, system, max_tokens, streaming)
- How **Server-Sent Events (SSE)** streaming works and why it matters for user experience

Key mental models to internalize:

- The API is a **pure function**: `f(messages) -> response`. No sessions, no state, no memory.
- **You** manage conversation history. The API does not remember previous calls.
- **Tokens** are the currency. You pay per input token and per output token. Understanding tokens changes how you design prompts.

Common misconceptions to avoid:

- "Claude remembers our previous conversation" -- No. Every API call is independent.
- "I need to start a session before making requests" -- No. There are no sessions.
- "The system prompt counts as free" -- No. System prompt tokens are billed as input tokens.

---

## 1. The API Contract -- Stateless Request/Response

### The Core Mental Model

The Anthropic Messages API follows a **stateless request/response** pattern. This is the single most important concept in this document. If you internalize one thing, let it be this:

> **Every API call is independent. The API has no memory of previous calls. The messages array you send IS the entire conversation.**

This is fundamentally different from how you interact with Claude on claude.com, where the chat interface maintains conversation history for you. Behind the scenes, even claude.com resends the entire conversation on each message. The API makes this explicit.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     STATELESS API MODEL                              │
│                                                                      │
│  Your Application                         Anthropic API              │
│  ┌─────────────┐                         ┌─────────────────┐        │
│  │             │   POST /v1/messages      │                 │        │
│  │  Build the  │ ──────────────────────►  │  Receive the    │        │
│  │  messages   │   {                      │  FULL context.  │        │
│  │  array.     │     messages: [          │                 │        │
│  │             │       {user: "Hi"},      │  Process.       │        │
│  │  Include    │       {asst: "Hello!"},  │                 │        │
│  │  EVERYTHING │       {user: "How..."}   │  Generate ONE   │        │
│  │  from the   │     ]                    │  response.      │        │
│  │  entire     │   }                      │                 │        │
│  │  convo.     │                          │  Return it.     │        │
│  │             │  ◄──────────────────────  │                 │        │
│  │  Append the │   {                      │  FORGET         │        │
│  │  response   │     content: [{          │  EVERYTHING.    │        │
│  │  to your    │       text: "..."        │                 │        │
│  │  local      │     }]                   │  No session.    │        │
│  │  array.     │   }                      │  No memory.     │        │
│  │             │                          │  No state.      │        │
│  └─────────────┘                         └─────────────────┘        │
│                                                                      │
│  KEY INSIGHT: The API is a pure function.                            │
│  f(system, messages, params) → response                              │
│  Same input → same output (modulo temperature)                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Why Stateless?

This design is intentional and has several consequences:

1. **Scalability**: Anthropic can route your request to any server. No sticky sessions, no session affinity. This is the same reason REST APIs are stateless.

2. **Reliability**: If a server crashes mid-request, you retry and it works. No session state to recover.

3. **Transparency**: You see exactly what the model sees. There is no hidden context, no secret system prompt, no accumulated state you cannot inspect.

4. **Cost predictability**: You pay for exactly the tokens you send. No background token usage from "maintaining a session."

5. **Flexibility**: You can modify conversation history before resending. Remove messages, edit them, inject system-level instructions mid-conversation. You are in full control.

### What This Means for Your Application

Your application is responsible for:

- **Storing** the conversation history (in memory, database, or both)
- **Constructing** the messages array for each API call
- **Appending** the model's response to your local history
- **Deciding** what to include or exclude from context

```
AI DOCTOR EXAMPLE:
When a doctor requests an AI briefing for a patient, the backend:

1. Loads the patient record from PostgreSQL (vitals, meds, labs, history)
2. Builds a messages array with the patient data as context
3. Sends ONE API call to Claude — no prior conversation needed
4. Receives the briefing response
5. Saves the result to the database

Each briefing is an independent API call. Claude does not "remember"
the previous patient or the previous briefing. The full patient context
is sent every time.
```

---

## 2. Authentication

### API Keys

Every request to the Anthropic API requires an **API key** passed in the `x-api-key` HTTP header. API keys are created in the [Anthropic Console](https://console.anthropic.com/) under API Keys.

Keys follow this format:

```
sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The prefix `sk-ant-` identifies it as an Anthropic secret key. Never commit this to version control. Never expose it in frontend JavaScript. Never log it.

### Using the Key

```bash
# The key goes in the x-api-key header (NOT Authorization: Bearer)
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: sk-ant-api03-your-key-here" \
  -H "anthropic-version: 2023-06-01" \
  ...
```

Note: Anthropic uses `x-api-key` as a custom header, **not** the standard `Authorization: Bearer` pattern that OpenAI and most other APIs use. This is a common source of confusion when switching between providers.

### Security Best Practices

| Practice | Why |
|----------|-----|
| Store keys in environment variables | Never hardcode in source code |
| Use `.env` files locally, add `.env` to `.gitignore` | Prevents accidental commits |
| Use Kubernetes Secrets or cloud secret managers in production | Encrypted at rest, access-controlled |
| Rotate keys periodically | Limits blast radius of leaked keys |
| Use separate keys for dev/staging/prod | Audit trail, independent rotation |
| Set spending limits in the Anthropic Console | Prevents runaway costs from bugs or abuse |
| Never send keys to the frontend | JavaScript is visible to users; keys go in backend only |

```bash
# Local development: .env file
echo "ANTHROPIC_API_KEY=sk-ant-api03-..." >> .env

# Usage in bash scripts
export ANTHROPIC_API_KEY=$(cat .env | grep ANTHROPIC_API_KEY | cut -d= -f2)

# Usage in Python (with python-dotenv or pydantic-settings)
import os
api_key = os.environ["ANTHROPIC_API_KEY"]
```

```
AI DOCTOR EXAMPLE:
The AI Doctor backend loads the API key from environment variables
using pydantic-settings. In local development, it reads from a .env
file. In Kubernetes, it comes from a Secret mounted as an env var.

The frontend NEVER sees the API key. The React app calls the
FastAPI backend, which calls Claude. The key lives only on the server.
```

### Claude.com Subscription vs API Billing

This confuses many people. They are **completely separate billing systems**:

| | Claude.com (claude.ai) | API (api.anthropic.com) |
|---|---|---|
| **What it is** | Chat interface in the browser | Programmatic HTTP API |
| **Billing** | Monthly subscription ($0/20/100) | Pay-per-token usage |
| **Authentication** | Email + password login | API key in header |
| **Who uses it** | Humans typing in a chat window | Your application code |
| **Rate limits** | Messages per day/hour | Tokens per minute, requests per minute |
| **Key takeaway** | Paying for Claude Pro does NOT give you API credits | API usage is billed separately |

You can have a Claude Pro subscription for personal use AND a separate API account with its own billing for your application. They do not share credits or quotas.

---

## 3. Making Your First Request

### Anatomy of a Request

Let us walk through a real API call, field by field. This script exists in the project at `scripts/test-tool-call.sh`:

```bash
#!/bin/bash

# Test Anthropic Messages API
# Usage: ANTHROPIC_API_KEY=sk-ant-... bash scripts/test-tool-call.sh

if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "Error: ANTHROPIC_API_KEY is not set"
  exit 1
fi

curl -s https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 1024,
    "messages": [
      { "role": "user", "content": "What is the weather in Tokyo?" }
    ]
  }' | jq .
```

### Required Headers

Every API request needs three headers:

| Header | Value | Purpose |
|--------|-------|---------|
| `content-type` | `application/json` | Request body is JSON |
| `x-api-key` | `sk-ant-api03-...` | Authentication |
| `anthropic-version` | `2023-06-01` | API version. Locks behavior to a known version so Anthropic can evolve the API without breaking your code. |

The `anthropic-version` header is a **version pin**. When Anthropic changes API behavior (response format, default values, etc.), they release a new version string. Your existing code keeps working because it is pinned to `2023-06-01`. When you are ready to upgrade, you change the header and adapt to any breaking changes.

### Required Body Fields

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 1024,
  "messages": [
    { "role": "user", "content": "What is the weather in Tokyo?" }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Which Claude model to use. See [Model Selection](#6-model-selection). |
| `max_tokens` | integer | Yes | Maximum number of tokens the model can generate. Acts as a hard ceiling -- the response will stop at this limit even mid-sentence. |
| `messages` | array | Yes | The conversation history. See [The Messages Array](#4-the-messages-array). |

**Why is `max_tokens` required?** Because generating tokens costs money. Without a limit, a model could generate thousands of tokens (and charge you for them) in response to a simple question. The required limit forces you to think about output length and cost.

### Running the Script

```bash
# Set your API key and run
ANTHROPIC_API_KEY=sk-ant-api03-... bash scripts/test-tool-call.sh
```

You should see a JSON response with Claude's answer. We will break down that response structure in [Section 5](#5-response-structure).

### Minimal Python Example

```python
import httpx

response = httpx.post(
    "https://api.anthropic.com/v1/messages",
    headers={
        "content-type": "application/json",
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
    },
    json={
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Explain blood pressure readings."}
        ],
    },
)

data = response.json()
print(data["content"][0]["text"])
```

This is the raw HTTP approach. In practice, you would use the official `anthropic` Python SDK, which handles headers, retries, and error parsing. But understanding the raw HTTP layer is essential -- the SDK is just a wrapper around these exact requests.

---

## 4. The Messages Array

### The Conversation IS the Array

The `messages` array is the single most important field in the request body. It represents the **entire conversation** from the model's perspective. There is nothing else. No hidden session state, no server-side memory. What you put in this array is literally all the model knows about this conversation.

### Role Alternation

Messages alternate between two roles:

- **`user`**: Messages from the human (or your application acting on behalf of the human)
- **`assistant`**: Messages from Claude (previous model responses that you are replaying)

The array **must** start with a `user` message. After that, roles must strictly alternate: `user`, `assistant`, `user`, `assistant`, ...

```json
{
  "messages": [
    {"role": "user",      "content": "What does high potassium mean?"},
    {"role": "assistant", "content": "Hyperkalemia (high potassium) can indicate..."},
    {"role": "user",      "content": "What level is dangerous?"},
    {"role": "assistant", "content": "Potassium levels above 6.0 mEq/L..."},
    {"role": "user",      "content": "What are the symptoms?"}
  ]
}
```

### Content Types

The `content` field can be a simple string (as shown above) or an array of **content blocks** for complex messages:

| Content Block Type | Used By | Purpose |
|-------------------|---------|---------|
| `text` | user, assistant | Plain text content |
| `image` | user | Base64 or URL image input |
| `tool_use` | assistant | Model requesting to call a tool |
| `tool_result` | user | Your app returning tool execution results |

Simple string content:
```json
{"role": "user", "content": "Hello"}
```

Array content with multiple blocks:
```json
{"role": "assistant", "content": [
  {"type": "text", "text": "Let me check that for you."},
  {"type": "tool_use", "id": "toolu_01Xyz...", "name": "get_weather", "input": {"city": "Tokyo"}}
]}
```

Tool use content blocks are covered in depth in `02-TOOL-USE-AND-AGENTIC-LOOP.md`.

### Why You Resend Everything

Because the API is stateless, **every call includes the full conversation history**. Here is what happens across three turns of a conversation:

```
TURN 1: User sends first message
┌─────────────────────────────────────┐
│ messages: [                         │
│   { user: "What is hypertension?" } │    ← 1 message sent
│ ]                                   │
└─────────────────────────────────────┘
                    │
                    ▼ API responds
            "Hypertension is high blood
             pressure, defined as..."

TURN 2: User follows up (you resend Turn 1 + response + new question)
┌──────────────────────────────────────────────┐
│ messages: [                                  │
│   { user: "What is hypertension?" },         │    ← resent
│   { assistant: "Hypertension is high..." },  │    ← resent (model's prev response)
│   { user: "What causes it?" }                │    ← new message
│ ]                                            │
└──────────────────────────────────────────────┘
                    │                               3 messages sent
                    ▼ API responds
            "Hypertension can be caused by..."

TURN 3: Another follow-up (you resend everything again)
┌──────────────────────────────────────────────┐
│ messages: [                                  │
│   { user: "What is hypertension?" },         │    ← resent
│   { assistant: "Hypertension is high..." },  │    ← resent
│   { user: "What causes it?" },               │    ← resent
│   { assistant: "Hypertension can be..." },   │    ← resent
│   { user: "How is it treated?" }             │    ← new message
│ ]                                            │
└──────────────────────────────────────────────┘
                                                    5 messages sent
```

Notice: the messages array **grows with every turn**. By turn 10, you are sending 19 messages (10 user + 9 assistant). This has cost implications -- you are paying for input tokens on every previous message *again*. This is why **prompt caching** (covered in `03-PROMPT-CACHING-AND-OPTIMIZATION.md`) is critical for multi-turn conversations.

### Conversation Flow Diagram

```mermaid
sequenceDiagram
    participant App as Your Application
    participant DB as Message Store
    participant API as Anthropic API

    Note over App: User types a question
    App->>DB: Load conversation history
    DB-->>App: Previous messages []
    App->>App: Append user message to array
    App->>API: POST /v1/messages { messages: [...] }
    API-->>App: { content: [...], stop_reason: "end_turn" }
    App->>App: Append assistant response to array
    App->>DB: Save updated conversation
    Note over API: API forgets everything immediately
```

```
AI DOCTOR EXAMPLE:
The AI Doctor does NOT maintain multi-turn conversations in V1.
Each briefing is a single-turn request:

messages: [
  { role: "user", content: "Here is the patient record: ... Generate a briefing." }
]

The entire patient context (vitals, meds, labs) goes into ONE user message.
Claude responds with the briefing. No follow-up turns. This keeps the
architecture simple and the cost predictable — one input, one output.

Multi-turn conversations (doctor asking follow-up questions about the briefing)
are a V2+ feature.
```

---

## 5. Response Structure

### Full Response Object

When the API returns a successful response, it looks like this:

```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Hypertension, or high blood pressure, is a condition where the force of blood against your artery walls is consistently too high. It is typically defined as a systolic pressure of 130 mmHg or higher, or a diastolic pressure of 80 mmHg or higher."
    }
  ],
  "model": "claude-sonnet-4-5-20250929",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 42,
    "output_tokens": 67,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

### Field-by-Field Breakdown

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier for this response. Format: `msg_01Xxx...`. Useful for logging, debugging, and support requests. |
| `type` | string | Always `"message"` for Messages API responses. |
| `role` | string | Always `"assistant"`. This is the response from Claude. |
| `content` | array | Array of content blocks. Usually one `text` block, but can include `tool_use` blocks (covered in Doc 02). |
| `model` | string | The model that generated this response. Confirms which model was used. |
| `stop_reason` | string | Why the model stopped generating. See below. |
| `stop_sequence` | string/null | If `stop_reason` is `"stop_sequence"`, this shows which sequence was matched. Otherwise `null`. |
| `usage` | object | Token counts for billing and monitoring. |

### stop_reason Values

The `stop_reason` field tells you *why* the model stopped generating text. This is critical for building correct application logic:

| Value | Meaning | What To Do |
|-------|---------|------------|
| `end_turn` | Model finished its response naturally | Normal completion. Use the response as-is. |
| `max_tokens` | Hit the `max_tokens` limit you set | Response is **truncated**. You may need to increase `max_tokens` or ask the model to continue. |
| `stop_sequence` | Matched a string you specified in `stop_sequences` | Custom stop. Used for structured output, code generation delimiters. |
| `tool_use` | Model wants to call a tool | The `content` array includes a `tool_use` block. You must execute the tool and send the result back. See Doc 02. |

```
┌────────────────────────────────────────────────────────────────┐
│                    stop_reason Decision Tree                    │
│                                                                │
│  Response received                                             │
│       │                                                        │
│       ├─ stop_reason: "end_turn"                               │
│       │   └─ ✓ Done. Display response to user.                 │
│       │                                                        │
│       ├─ stop_reason: "max_tokens"                             │
│       │   └─ ⚠ Response truncated! Consider:                   │
│       │       ├─ Increase max_tokens                           │
│       │       ├─ Ask model to continue                         │
│       │       └─ Break request into smaller pieces             │
│       │                                                        │
│       ├─ stop_reason: "tool_use"                               │
│       │   └─ Model wants to call a function.                   │
│       │       ├─ Parse tool_use block from content              │
│       │       ├─ Execute the function locally                   │
│       │       ├─ Send tool_result back to API                   │
│       │       └─ (This is the agentic loop — see Doc 02)       │
│       │                                                        │
│       └─ stop_reason: "stop_sequence"                          │
│           └─ Matched your custom stop string.                  │
│               └─ Parse output up to the stop point.            │
└────────────────────────────────────────────────────────────────┘
```

### Usage Tokens

The `usage` object tracks token consumption:

```json
{
  "usage": {
    "input_tokens": 42,
    "output_tokens": 67,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

| Field | Description |
|-------|-------------|
| `input_tokens` | Tokens in your request (system + messages). You pay per input token. |
| `output_tokens` | Tokens in the model's response. You pay per output token (typically 3-5x the input price). |
| `cache_creation_input_tokens` | Tokens written to the prompt cache on this request. Billed at 1.25x input price. |
| `cache_read_input_tokens` | Tokens read from the prompt cache instead of reprocessing. Billed at 0.1x input price (90% savings). |

Caching fields are covered in depth in `03-PROMPT-CACHING-AND-OPTIMIZATION.md`.

```
AI DOCTOR EXAMPLE:
For the AI Doctor, the usage field is critical for cost monitoring.

A typical briefing request might use:
  - input_tokens: ~2,000 (patient record + system prompt + instructions)
  - output_tokens: ~800 (the generated briefing)

At Sonnet pricing ($3/MTok input, $15/MTok output):
  - Input cost:  2,000 × $3/1,000,000  = $0.006
  - Output cost: 800 × $15/1,000,000 = $0.012
  - Total per briefing: ~$0.018 (less than 2 cents)

Tracking usage per request lets you estimate: "At 500 briefings/day,
our monthly Claude API cost is ~$270."
```

---

## 6. Model Selection

### The Claude Model Family

Anthropic offers three tiers of Claude models, each optimized for different tradeoffs between capability, speed, and cost:

```
┌──────────────────────────────────────────────────────────────────┐
│                     CLAUDE MODEL TIERS                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  OPUS                                                     │   │
│  │  Highest capability. Deep reasoning, complex analysis.    │   │
│  │  Slowest. Most expensive. Use for hard problems.          │   │
│  │  Model ID: claude-opus-4-6                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SONNET                                                   │   │
│  │  Best balance. Strong reasoning at moderate cost.         │   │
│  │  Good speed. The default choice for most applications.    │   │
│  │  Model ID: claude-sonnet-4-5-20250929                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  HAIKU                                                    │   │
│  │  Fastest. Cheapest. Good for simple tasks.                │   │
│  │  Classification, extraction, summarization.               │   │
│  │  Model ID: claude-haiku-4-5-20251001                      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Capability:  Opus >>>>>> Sonnet >>>> Haiku                     │
│  Speed:       Haiku >>>> Sonnet >> Opus                          │
│  Cost:        Haiku <<<< Sonnet << Opus                          │
└──────────────────────────────────────────────────────────────────┘
```

### Model Comparison

| Attribute | Opus | Sonnet | Haiku |
|-----------|------|--------|-------|
| **Model ID** | `claude-opus-4-6` | `claude-sonnet-4-5-20250929` | `claude-haiku-4-5-20251001` |
| **Reasoning** | Best. Complex multi-step reasoning, nuance, edge cases | Strong. Handles most reasoning tasks well | Basic. Simple classification, extraction, formatting |
| **Speed (TTFT)** | Slowest (~2-5s first token) | Moderate (~0.5-2s first token) | Fastest (~0.2-0.5s first token) |
| **Input Price** | $15/MTok | $3/MTok | $0.80/MTok |
| **Output Price** | $75/MTok | $15/MTok | $4/MTok |
| **Context Window** | 200K tokens | 200K tokens | 200K tokens |
| **Best For** | Research, analysis, complex code, medical reasoning | General-purpose, tool use, content generation | Classification, routing, extraction, high-volume |

*MTok = million tokens. Prices as of 2025. Check [Anthropic pricing](https://www.anthropic.com/pricing) for current rates.*

### Model ID Format

Model IDs follow a pattern: `claude-{tier}-{version}`. The version includes a date stamp:

```
claude-sonnet-4-5-20250929
│       │     │ │ │
│       │     │ │ └─ Date: September 29, 2025
│       │     │ └─ Minor version: 5
│       │     └─ Major version: 4
│       └─ Tier: sonnet (mid-range)
└─ Family: claude
```

Anthropic periodically releases updated models with improved capabilities. By pinning to a specific model ID (with the date), your application behavior stays consistent even as new versions are released. When you are ready to upgrade, you change the model string and test.

### When to Use Which

```mermaid
flowchart TD
    A[New API Request] --> B{What kind of task?}
    B -->|Complex reasoning, analysis,\n safety-critical decisions| C[Use Opus]
    B -->|General purpose,\n tool use, coding| D[Use Sonnet]
    B -->|Simple classification,\n extraction, routing| E[Use Haiku]

    C --> F{Cost acceptable?}
    F -->|Yes| G[Opus]
    F -->|No| H[Try Sonnet first.\n Upgrade to Opus only\n if quality insufficient.]

    D --> I[Sonnet\n Best default choice]

    E --> J{Quality sufficient?}
    J -->|Yes| K[Haiku\n Lowest cost]
    J -->|No| L[Upgrade to Sonnet]
```

**Rules of thumb:**

1. **Start with Sonnet.** It handles 80%+ of use cases well.
2. **Drop to Haiku** for high-volume, simple tasks (classification, extraction, reformatting).
3. **Escalate to Opus** for tasks where Sonnet's quality is not sufficient (complex reasoning, nuanced analysis, hard coding problems).
4. **Never start with Opus** unless you know the task demands it. You will waste money on most requests.

```
AI DOCTOR EXAMPLE:
The AI Doctor V1 uses Sonnet for generating patient briefings.

Why not Opus?
  - Briefings are structured (vitals summary, medication review, flags)
  - Sonnet handles this level of medical reasoning well
  - Cost: ~$0.018/briefing with Sonnet vs ~$0.09/briefing with Opus
  - At 500 briefings/day: $270/month (Sonnet) vs $1,350/month (Opus)

Why not Haiku?
  - Medical reasoning needs nuance (drug interactions, lab trend analysis)
  - Haiku might miss subtle flags that Sonnet catches
  - Patient safety > cost savings

For V2+ features like multi-agent tool use or complex differential
diagnosis, Opus might be justified for specific high-stakes calls.
```

---

## 7. Configuration Parameters

Beyond the required `model`, `max_tokens`, and `messages`, the API accepts several optional parameters that control how the model generates text.

### system (System Prompt)

The **system prompt** is a special instruction that sets the model's behavior, role, and constraints. It appears before the messages array in the model's context and persists across all turns.

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 1024,
  "system": "You are a medical AI assistant helping doctors review patient records. Be precise, cite specific values from the patient data, and flag any values outside normal ranges. Never provide patient care advice directly to patients.",
  "messages": [
    {"role": "user", "content": "Review this patient record: ..."}
  ]
}
```

**Key points about system prompts:**

- The system prompt is **not free**. Its tokens count as input tokens and you pay for them on every request.
- It is sent on **every API call**. In a multi-turn conversation, the system prompt tokens are re-billed each turn.
- The model treats system instructions with **higher priority** than user messages (but not absolute -- prompt injection is still possible).
- You can change the system prompt between turns if needed (since each call is independent).

```
AI DOCTOR EXAMPLE:
The AI Doctor's system prompt defines Claude's role:

system: "You are a clinical decision support AI. Given a patient record,
generate a structured pre-visit briefing. Include: 1) Vital signs summary
with out-of-range flags, 2) Medication review with interaction checks,
3) Recent lab results with trend analysis, 4) Suggested discussion points.
All flags must include source: 'ai'. Never log patient data."

This system prompt is ~80 tokens. At $3/MTok (Sonnet input), that is
$0.00024 per request — negligible. But for a 2,000-token system prompt
sent 500 times/day, that is $0.90/day just for system prompt tokens.
Prompt caching (Doc 03) reduces this by 90%.
```

### temperature

**Temperature** controls the randomness of the model's output. It is a float between `0.0` and `1.0`:

| Value | Behavior | Use Case |
|-------|----------|----------|
| `0.0` | Deterministic. Most likely token at each step. Minimal variation. | Factual extraction, classification, structured output |
| `0.3-0.5` | Low randomness. Mostly predictable with slight variation. | Medical summaries, technical writing, code generation |
| `0.7` | Moderate randomness. Good balance of creativity and coherence. Default. | General conversation, creative writing, brainstorming |
| `1.0` | High randomness. More diverse, surprising, sometimes incoherent. | Creative fiction, poetry, divergent brainstorming |

**How it works (simplified):** At each step, the model computes a probability distribution over all possible next tokens. Temperature scales these probabilities before sampling:

```
Token probabilities before temperature scaling:
  "hypertension"  → 0.45
  "high"          → 0.30
  "elevated"      → 0.15
  "increased"     → 0.08
  "abnormal"      → 0.02

At temperature 0.0: Always picks "hypertension" (highest probability)
At temperature 0.5: Usually "hypertension", sometimes "high"
At temperature 1.0: Picks proportional to original probabilities
```

The mathematical details of temperature scaling are covered in `05-TRANSFORMER-ARCHITECTURE.md`.

### top_p (Nucleus Sampling)

**top_p** limits the model to sampling from the smallest set of tokens whose cumulative probability exceeds `p`. This is an alternative to temperature for controlling randomness.

```
Sorted token probabilities:
  "hypertension"  → 0.45  (cumulative: 0.45)
  "high"          → 0.30  (cumulative: 0.75)
  "elevated"      → 0.15  (cumulative: 0.90)  ← top_p=0.9 cuts here
  "increased"     → 0.08  (cumulative: 0.98)
  "abnormal"      → 0.02  (cumulative: 1.00)

With top_p=0.9: Model samples only from {"hypertension", "high", "elevated"}
With top_p=0.5: Model samples only from {"hypertension"}
```

**Recommendation:** Use temperature OR top_p, not both together. They interact in non-obvious ways. Anthropic recommends `temperature` as the primary knob.

### top_k

**top_k** limits the model to sampling from the top K most probable tokens at each step.

```
With top_k=3: Model samples only from the top 3 tokens
  "hypertension"  → 0.45
  "high"          → 0.30
  "elevated"      → 0.15
  (all others excluded)
```

Less commonly used than temperature or top_p. Useful when you want hard limits on token diversity.

### max_tokens

The **maximum number of output tokens** the model can generate. Required field.

```json
{"max_tokens": 1024}
```

- If the model finishes its response in fewer tokens, it stops normally (`stop_reason: "end_turn"`).
- If the model hits this limit, it stops mid-generation (`stop_reason: "max_tokens"`). The response may be truncated mid-sentence.
- Setting this too low risks truncated responses. Setting it too high risks unexpected cost.
- This does NOT limit input tokens. Only output.

### stop_sequences

An array of strings that cause the model to stop generating when encountered:

```json
{
  "stop_sequences": ["\n\nHuman:", "```end"]
}
```

When the model generates any string in this array, it stops immediately and returns `stop_reason: "stop_sequence"`. The matched string is NOT included in the output.

Use cases:
- Preventing the model from simulating additional conversation turns
- Delimiting structured output (stop at a closing tag)
- Building parseable output formats

### stream

A boolean that enables **Server-Sent Events (SSE)** streaming:

```json
{"stream": true}
```

When `true`, the API returns a stream of events instead of a single JSON response. Each event contains a partial token or status update. This enables real-time display of the model's output as it is generated, rather than waiting for the complete response. See [Section 8](#8-streaming-sse) for details.

### metadata

Optional object for tracking and billing:

```json
{
  "metadata": {
    "user_id": "doctor-42"
  }
}
```

The `user_id` field helps Anthropic detect and prevent abuse. It should be a stable identifier for the end user (not PII). Anthropic may use this for rate limiting per user.

### Full Parameter Reference

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 2048,
  "system": "You are a helpful medical AI assistant.",
  "messages": [
    {"role": "user", "content": "Explain blood pressure."}
  ],
  "temperature": 0.3,
  "top_p": 0.9,
  "top_k": 40,
  "stop_sequences": ["\n\nHuman:"],
  "stream": false,
  "metadata": {"user_id": "doctor-42"}
}
```

**Parameter interaction summary:**

| Parameter | Controls | Typical Production Value |
|-----------|----------|------------------------|
| `temperature` | Output randomness | `0.0-0.3` for factual, `0.7` for creative |
| `top_p` | Nucleus sampling threshold | `0.9` (or omit and use temperature) |
| `top_k` | Hard limit on token candidates | Rarely set; omit in most cases |
| `max_tokens` | Output length ceiling | Match expected output size + buffer |
| `system` | Model persona and instructions | Always set for production apps |
| `stop_sequences` | Early termination triggers | Only when needed for parsing |
| `stream` | Real-time token delivery | `true` for UX, `false` for batch |

---

## 8. Streaming (SSE)

### Why Streaming Matters

Without streaming, the user experience looks like this:

```
User clicks "Generate Briefing"
     │
     ▼
[                              ] ← Spinner for 3-8 seconds
[         Loading...           ]   User sees NOTHING until
[                              ]   the entire response is ready
     │
     ▼
Full briefing appears all at once
```

With streaming, the user experience looks like this:

```
User clicks "Generate Briefing"
     │
     ▼  (200ms later, first tokens appear)
"Based on the patient's recent..."
     │  (tokens continue appearing in real-time)
"Based on the patient's recent vitals, blood pressure is..."
     │
"Based on the patient's recent vitals, blood pressure is elevated
at 158/92 mmHg. This represents..."
     │
     ▼  (complete in 3-8 seconds, but user has been reading the whole time)
Full briefing displayed
```

The total time is the same. But the *perceived* latency drops from 3-8 seconds to ~200ms because the user sees the first token almost immediately.

### How SSE Works

**Server-Sent Events (SSE)** is an HTTP standard for streaming data from server to client over a single long-lived connection. Unlike WebSockets, SSE is unidirectional (server to client only) and uses standard HTTP. This makes it simple, reliable, and firewall-friendly.

When you set `"stream": true`, the API response is no longer a single JSON object. Instead, it is a stream of text events:

```
┌──────────────────────────────────────────────────────────────────┐
│                      SSE EVENT FLOW                              │
│                                                                  │
│  Your App                              Anthropic API             │
│     │                                       │                    │
│     │  POST /v1/messages {stream: true}     │                    │
│     │ ─────────────────────────────────────► │                    │
│     │                                       │                    │
│     │  event: message_start                 │                    │
│     │  data: {type:"message", id:"msg_01"}  │  ◄── Message      │
│     │ ◄──────────────────────────────────── │      metadata      │
│     │                                       │                    │
│     │  event: content_block_start           │                    │
│     │  data: {type:"text", index:0}         │  ◄── Text block    │
│     │ ◄──────────────────────────────────── │      begins        │
│     │                                       │                    │
│     │  event: content_block_delta           │                    │
│     │  data: {delta:{text:"Based "}}        │  ◄── Token 1       │
│     │ ◄──────────────────────────────────── │                    │
│     │                                       │                    │
│     │  event: content_block_delta           │                    │
│     │  data: {delta:{text:"on "}}           │  ◄── Token 2       │
│     │ ◄──────────────────────────────────── │                    │
│     │                                       │                    │
│     │  event: content_block_delta           │                    │
│     │  data: {delta:{text:"the "}}          │  ◄── Token 3       │
│     │ ◄──────────────────────────────────── │                    │
│     │                                       │                    │
│     │         ... more deltas ...           │                    │
│     │                                       │                    │
│     │  event: content_block_stop            │                    │
│     │  data: {index:0}                      │  ◄── Block done    │
│     │ ◄──────────────────────────────────── │                    │
│     │                                       │                    │
│     │  event: message_delta                 │                    │
│     │  data: {stop_reason:"end_turn",       │  ◄── Final         │
│     │         usage:{output_tokens:67}}     │      metadata      │
│     │ ◄──────────────────────────────────── │                    │
│     │                                       │                    │
│     │  event: message_stop                  │                    │
│     │  data: {}                             │  ◄── Stream ends   │
│     │ ◄──────────────────────────────────── │                    │
│     │                                       │                    │
└──────────────────────────────────────────────────────────────────┘
```

### Event Types

| Event | When | Data Contains |
|-------|------|---------------|
| `message_start` | First event in the stream | Message `id`, `model`, `role`, `usage` (input tokens) |
| `content_block_start` | A new content block begins | Block `type` (`"text"` or `"tool_use"`), `index` |
| `content_block_delta` | Token(s) generated | Partial text or tool input JSON |
| `content_block_stop` | A content block is complete | Block `index` |
| `message_delta` | Message-level metadata update | `stop_reason`, `usage` (output tokens) |
| `message_stop` | Stream complete | Empty. Close the connection. |
| `ping` | Keepalive | Empty. Sent periodically to keep the connection open. |

### Raw SSE Format

Each event in the stream is a plain text block following the SSE specification:

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_01XFDUDYJgAACzvnptvVoYEL","type":"message","role":"assistant","content":[],"model":"claude-sonnet-4-5-20250929","stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":42,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hypertension"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" is"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" high"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" blood"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" pressure."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"output_tokens":5}}

event: message_stop
data: {"type":"message_stop"}
```

Notice: each delta typically contains one or a few tokens of text. Your frontend appends each delta to the display buffer in real-time.

### Consuming an SSE Stream with curl

```bash
# The --no-buffer flag prevents curl from buffering the response
# Without it, curl may wait to collect output before printing

curl -s --no-buffer https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 256,
    "stream": true,
    "messages": [
      {"role": "user", "content": "What is hypertension?"}
    ]
  }'
```

This prints the raw SSE events to your terminal as they arrive. You will see `event:` and `data:` lines appearing in real-time.

### Consuming SSE in Python

```python
import httpx

with httpx.stream(
    "POST",
    "https://api.anthropic.com/v1/messages",
    headers={
        "content-type": "application/json",
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
    },
    json={
        "model": "claude-sonnet-4-5-20250929",
        "max_tokens": 1024,
        "stream": True,
        "messages": [{"role": "user", "content": "What is hypertension?"}],
    },
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data["type"] == "content_block_delta":
                print(data["delta"]["text"], end="", flush=True)
    print()  # newline at the end
```

### When to Stream vs Not Stream

| Scenario | Stream? | Why |
|----------|---------|-----|
| User-facing chat interface | Yes | Perceived latency drops from seconds to milliseconds |
| Background batch processing | No | No human watching; simpler code; easier error handling |
| API-to-API calls (your backend calling Claude) | Depends | Stream if you are forwarding to a frontend; skip if processing the full response |
| Testing/debugging | No | Easier to inspect the full JSON response |

```
AI DOCTOR EXAMPLE:
The AI Doctor V1 does NOT use streaming. The frontend shows a spinner
while the backend makes a synchronous POST to Claude and waits for the
full response. This is simpler to implement and sufficient for V1.

V2 may add streaming for the briefing generation step — the doctor
would see the briefing "typing out" in real-time instead of waiting
for a spinner. This requires:
  1. Backend: Forward SSE events from Claude API to frontend
  2. Frontend: Consume SSE stream and render incrementally
  3. State management: Handle partial briefings, errors mid-stream
```

---

## 9. Summary

### What We Covered

This document established the foundational knowledge for working with the Anthropic Messages API:

| Concept | Key Takeaway |
|---------|-------------|
| **Stateless API** | Every call is independent. The messages array IS the conversation. No sessions, no memory. |
| **Authentication** | API key in `x-api-key` header. Never expose to frontend. Separate from claude.com billing. |
| **Request anatomy** | Three required headers, three required body fields (`model`, `max_tokens`, `messages`). |
| **Messages array** | Alternating user/assistant roles. Grows with each turn. You resend everything. |
| **Response structure** | `content` array with text/tool_use blocks. `stop_reason` drives application logic. `usage` for cost tracking. |
| **Model selection** | Sonnet for most tasks. Haiku for high-volume simple work. Opus for hard reasoning. |
| **Parameters** | `temperature` for randomness, `system` for persona, `max_tokens` for output ceiling, `stream` for real-time output. |
| **Streaming (SSE)** | Real-time token delivery. Reduces perceived latency. Six event types to handle. |

### Cost Awareness

Every API call has a cost. Understanding the token-based pricing model is essential:

```
Cost = (input_tokens × input_price) + (output_tokens × output_price)

Sonnet example:
  2,000 input tokens × $3/MTok  = $0.006
  +  800 output tokens × $15/MTok = $0.012
  = $0.018 per request

At 1,000 requests/day × 30 days = $540/month
```

The biggest cost lever is **input tokens** in multi-turn conversations (resending history) and **prompt caching** (90% input cost reduction). Both are covered in `03-PROMPT-CACHING-AND-OPTIMIZATION.md`.

---

**Next Steps**: Proceed to `02-TOOL-USE-AND-AGENTIC-LOOP.md` to learn how Claude can call functions, execute code, and interact with external systems through the tool use API. This is where the API transforms from "question in, answer out" to "agent that can take actions."
