# Module 5 — Skills & Sandboxes

This module covers the two primitives that turn agents from "smart chatbots" into systems that *do* things: **skills** (modular capabilities the agent loads on demand) and **sandboxes** (controlled environments where the agent's actions execute).

The doctor-assistant agent in this repo gets you through Modules 1-4 without sandboxing — because its tool surface is bounded by Pydantic-validated structured output and MCP tool calls, the blast radius is already small. Module 5 is where you learn what to do when the tool surface widens — when an agent needs to run code, manipulate files, or operate over an arbitrary computer.

## Skills (Claude Code skills)

Already covered live in [`.claude/skills/`](../../.claude/skills/) — see those examples for the canonical shape. Skills are progressive-disclosure capabilities: each skill is a `SKILL.md` file with frontmatter (name, description) plus a body the agent loads only when triggered. The metadata costs ~100 tokens; the body costs nothing until invoked.

The contrast with MCP tools (covered in Module 3) is important. Both extend the agent. But MCP tool definitions sit in the model's context every turn (~150-800 tokens per tool); skill metadata is dormant. For agents with 10+ capabilities, skills + a router scale better than MCP tools alone.

## Sandboxes

A sandbox is an isolation boundary around code the agent runs. The choice you make is not just "which vendor" but "which **scope**" and "which **isolation tier**." Most "sandbox for agents" writeups conflate these.

### Three scopes

- **Code-execution scope (narrow)** — only the LLM-generated code runs isolated. The agent loop and credentials live on the host. E2B, Modal, Anthropic's `code_execution` tool, OpenAI's Code Interpreter sit here by default.
- **Tool-execution scope (medium)** — every tool invocation runs isolated, including shell, file-write, HTTP. Claude Code's [`sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime) is the canonical example. The reasoning loop runs on the host; every action crosses an isolation boundary.
- **Full-agent scope (wide)** — the entire agent runtime (model client, tool dispatcher, memory, credentials) runs inside the sandbox. The host only sees input/output. Morph Labs, Fly Sprites, and OpenAI's `SandboxAgent` approach this.

Pick by threat model:
- **Public chatbot running user-supplied code** → code-execution scope is enough.
- **Local CLI agent on a developer's machine** → tool-execution scope (Claude Code does this by default).
- **Agent that processes untrusted third-party input** (emails, web pages, PDFs) → full-agent scope, because prompt injection is a data-flow attack and only wide scope blocks the data path.

### Five isolation tiers

| Tier | Primitive | Where it shows up |
|------|-----------|-------------------|
| 1. Language-VM | Deno permissions, Pyodide, WASM | Text-only agents |
| 2. Process | seccomp, Linux Landlock, macOS Seatbelt, bubblewrap | Claude Code, Codex CLI |
| 3. Container | runc + namespaces | Docker, Cloudflare Containers, GKE pods |
| 4. Kernel-userspace | gVisor | Modal, Anthropic `code_execution`, GKE Sandbox |
| 5. Hardware | Firecracker, Cloud Hypervisor microVMs | E2B, Vercel Sandbox, Fly Sprites |

Tiers 2 and 5 dominate 2026: tier 2 for local CLI agents (no VM tax), tier 5 for cloud multi-tenant.

### Five orthogonal axes (beyond the runtime)

The runtime tier is one decision. Whether your agent is *actually* sandboxed depends on five more:
1. **Network egress policy** — default-deny, CIDR allowlist, or open?
2. **Filesystem scoping** — ephemeral, persistent, or fork-from-snapshot?
3. **Secrets handling** — whose credentials does the sandbox see at runtime?
4. **Tool-call sandboxing** — which tools can the model re-invoke from inside?
5. **Snapshot/fork semantics** — does the snapshot capture `/dev/shm`? RAM? FDs?

## Picking a sandbox for the doctor agent

The doctor assistant in this repo currently doesn't run code. But there's a clear use case where adding a sandbox would make it more capable:

**Lab trend analysis.** Today the agent looks at lab values one-at-a-time and flags anything outside reference range. A more useful behavior: compute *trends* — "patient's HbA1c has dropped 1.2% over six months," "eGFR is falling 3 mL/min/year." LLMs do arithmetic poorly. A sandboxed Python environment does it correctly.

**Recommended provider for this use case: E2B.** Reasoning:
- **Free $100 of credits at signup, no card required** — works for learners.
- **Cheapest cold-start in our benchmarks** (~756 ms median; see the [companion repo](https://github.com/ramanshrivastava/sandboxes)).
- **Simplest dependency** — `pip install e2b`, single env var `E2B_API_KEY`.
- **Strong Python support** — Pyodide-style Python sandboxes don't have all of NumPy / pandas; E2B's Firecracker microVM does.
- **Tier 5 (hardware microVM)** — appropriate for code we don't fully trust the model to write.

Honest limitations: E2B's snapshot-fork primitive *captures `/dev/shm` byte-for-byte*. If a future iteration of the agent stores secrets in `/dev/shm` and snapshot-forks workers, those secrets propagate to all forks. Not a problem for the lab-trend use case (no secrets in `/dev/shm`), but a constraint to know. The full audit is in the [`sandboxes` repo's fork audit results](https://github.com/ramanshrivastava/sandboxes/blob/main/fork_audit/results_fork.md).

See [`backend/src/agents/sandbox_lab_trends.py.example`](../../backend/src/agents/sandbox_lab_trends.py.example) for a reference integration showing how to wire E2B into the existing Claude Agent SDK loop. It's named `.example` because dropping it into `backend/src/agents/` and importing it is a one-line change to enable the new behavior — but the choice of when to enable it (and which sandbox provider to use) is yours.

## Reproducing the benchmark numbers

Every claim above about cold-starts and fork-audit results is reproducible. The companion repo at [github.com/ramanshrivastava/sandboxes](https://github.com/ramanshrivastava/sandboxes) ships:

- `python/sandboxes/benchmark.py` — declarative provider registry; runs N=10 iterations across every configured provider, merges into `results.json`
- `fork_audit/fork_harness.py` — runs `/dev/shm` + `/tmp` + env + entropy probes against each provider's snapshot-fork primitive
- `run_all.sh` — single-command orchestrator

Run `bash run_all.sh` after `cp .env.example .env && cd python && uv sync` to reproduce.

## Related reading

- [Sandboxes for AI agents: what I measured across seven providers](https://ramanshrivastava.com/blog/sandboxes-for-ai-agents) — the writeup these benchmarks back
- [OpenAI Agents SDK announcement (2026-04-15)](https://openai.com/index/the-next-evolution-of-the-agents-sdk/) — `SandboxAgent` + integrations for the seven providers benchmarked
- [`sandbox-runtime` (anthropic-experimental)](https://github.com/anthropic-experimental/sandbox-runtime) — the tier-2 primitive Claude Code uses internally
- [Firecracker microVM paper, NSDI '20](https://www.usenix.org/system/files/nsdi20-paper-agache.pdf) — the foundation of tier-5
