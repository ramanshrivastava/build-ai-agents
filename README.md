# Build AI Agents

> Learn to build AI agents from foundations to full autonomy — by building a real doctor assistant with Claude Agent SDK, FastAPI, and React 19.

This repo is a structured learning path from transformer basics to autonomous coding agents. Each module builds on the previous one, with 20+ in-depth learning docs, live code you can run, and real agentic engineering workflows.

---

## Syllabus

### Module 1: Transformer Foundations

> Strong basics are non-negotiable before building agents.

| Resource | What You'll Learn |
|----------|-------------------|
| [`docs/agent-arch/05-TRANSFORMER-ARCHITECTURE.md`](docs/agent-arch/05-TRANSFORMER-ARCHITECTURE.md) | Tokenization, attention, FFN, generation |
| [`docs/agent-arch/06-TRAINING-AND-RUNNING-MODELS.md`](docs/agent-arch/06-TRAINING-AND-RUNNING-MODELS.md) | Pre-training, fine-tuning, RLHF, inference |
| [`docs/agent-arch/01-ANTHROPIC-API-FUNDAMENTALS.md`](docs/agent-arch/01-ANTHROPIC-API-FUNDAMENTALS.md) | Messages API, structured output, streaming |

### Module 2: RAG (Retrieval-Augmented Generation)

> The first enterprise use case of LLMs since 2022. Immediately useful at work.

| Resource | What You'll Learn |
|----------|-------------------|
| `docs/agent-arch/07-RAG-FUNDAMENTALS.md` | *Coming soon* — embeddings, vector DBs, chunking, retrieval |

### Module 3: Agentic Workflows

> Rigid workflows with some agentic control + MCP integration.

| Resource | What You'll Learn |
|----------|-------------------|
| [`docs/agent-arch/02-TOOL-USE-AND-AGENTIC-LOOP.md`](docs/agent-arch/02-TOOL-USE-AND-AGENTIC-LOOP.md) | Tool calling, agentic loops, orchestration |
| [`docs/agent-arch/03-PROMPT-CACHING-AND-OPTIMIZATION.md`](docs/agent-arch/03-PROMPT-CACHING-AND-OPTIMIZATION.md) | Caching, batching, cost optimization |
| [`docs/agent-arch/04-MCP-AND-A2A-PROTOCOLS.md`](docs/agent-arch/04-MCP-AND-A2A-PROTOCOLS.md) | MCP servers/clients, A2A protocol |
| [`backend/src/services/briefing_service.py`](backend/src/services/briefing_service.py) | **Live code** — real agent with structured output |
| [`docs/SCOPE-V1.md`](docs/SCOPE-V1.md) | How the agentic workflow was planned and built |

### Module 4: Full Agents (Human-in-the-Loop)

> Agent has full control + human oversight + hooks for safety.

| Resource | What You'll Learn |
|----------|-------------------|
| [`backend/src/`](backend/src/) | **Live code** — the doctor assistant agent |
| `docs/agent-arch/08-FULL-AGENTS-HITL.md` | *Coming soon* — agent autonomy, HITL patterns, hooks |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture vision (V1 → V2+) |

### Module 5: Full Agents (Skills + Sandboxes)

> The next 3-6 months of agent evolution.

| Resource | What You'll Learn |
|----------|-------------------|
| [`.claude/skills/`](.claude/skills/) | **Live examples** — custom Claude Code skills |
| `docs/agent-arch/09-SKILLS-AND-SANDBOXES.md` | *Coming soon* — skill systems, sandboxed execution |

### Module 6: Coding Agents

> Agents.md + tools + repo structure for AI-first development.

| Resource | What You'll Learn |
|----------|-------------------|
| [`CLAUDE.md`](CLAUDE.md) | **Live config** — how to instruct a coding agent |
| [`.claude/settings.json`](.claude/settings.json) | Hooks, permissions, environment |
| [`docs/PLAN-ITERATION-3.md`](docs/PLAN-ITERATION-3.md) | AI-first dev environment setup |
| [`docs/PLAN-ITERATION-1.md`](docs/PLAN-ITERATION-1.md) → [`2.md`](docs/PLAN-ITERATION-2.md) → [`3.md`](docs/PLAN-ITERATION-3.md) | How planning evolves across iterations |
| `docs/agent-arch/10-CODING-AGENTS.md` | *Coming soon* — agents.md, tools, repo patterns |

### Module 7: Personal Agents

> Build your own autonomous agents — OpenClaw, personal setup agents, etc.

| Resource | What You'll Learn |
|----------|-------------------|
| `docs/agent-arch/11-PERSONAL-AGENTS.md` | *Coming soon* — OpenClaw, personal automation agents, setup agents |

### Not Covered (Explore on Your Own)

- **Low-code agent builders** — N8N is very popular for visual workflow automation

---

## Bonus: Infrastructure & Kubernetes

> 13-doc series on deploying AI agents to production.

| # | Resource | Topics |
|---|----------|--------|
| 00 | [`00-OVERVIEW.md`](docs/infra-arch/00-OVERVIEW.md) | Series overview, prerequisites, reading paths |
| 01 | [`01-KUBERNETES-FUNDAMENTALS.md`](docs/infra-arch/01-KUBERNETES-FUNDAMENTALS.md) | Pods, Deployments, Services, ConfigMaps, Secrets |
| 02 | [`02-KUBERNETES-INTERNALS.md`](docs/infra-arch/02-KUBERNETES-INTERNALS.md) | Control plane, etcd, scheduler, controllers |
| 03 | [`03-GKE-AND-GCP.md`](docs/infra-arch/03-GKE-AND-GCP.md) | Managed K8s, Autopilot vs Standard, GCP services |
| 04 | [`04-TOOL-ECOSYSTEM.md`](docs/infra-arch/04-TOOL-ECOSYSTEM.md) | gcloud, kubectl, k9s, Helm, Kustomize, ArgoCD |
| 05 | [`05-APP-ON-K8S.md`](docs/infra-arch/05-APP-ON-K8S.md) | Map AI Doctor to K8s manifests and design decisions |
| 06 | [`06-DEPLOYMENT-PIPELINE.md`](docs/infra-arch/06-DEPLOYMENT-PIPELINE.md) | Dockerfiles, multi-stage builds, GitHub Actions CI/CD |
| 07 | [`07-GPU-AND-AGENTS.md`](docs/infra-arch/07-GPU-AND-AGENTS.md) | GPU nodes, agent workload isolation strategies |
| 08 | [`08-KNOWLEDGE-CHECK.md`](docs/infra-arch/08-KNOWLEDGE-CHECK.md) | 55+ questions: fundamentals, debugging, security |
| 09 | [`09-LOCAL-DEV-AND-IAC.md`](docs/infra-arch/09-LOCAL-DEV-AND-IAC.md) | minikube, kind, Skaffold, Terraform vs Pulumi |
| 10 | [`10-NGINX-PROXIES-AND-INGRESS.md`](docs/infra-arch/10-NGINX-PROXIES-AND-INGRESS.md) | Web servers, nginx deep dive, Ingress controllers |
| 11 | [`11-SECURITY-DISCOVERY-AND-WHY-K8S.md`](docs/infra-arch/11-SECURITY-DISCOVERY-AND-WHY-K8S.md) | 5-layer security, service discovery, VM vs K8s |
| 12 | [`12-DEPLOYING-ALONGSIDE-PORTFOLIO.md`](docs/infra-arch/12-DEPLOYING-ALONGSIDE-PORTFOLIO.md) | Subdomain architecture, managed DB internals |
| 13 | [`13-INFR-ARCH-ITERATION-01.md`](docs/infra-arch/13-INFR-ARCH-ITERATION-01.md) | Infrastructure architecture iteration |

---

## Quick Start

### Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Docker (for PostgreSQL)
- A Claude API key from [console.anthropic.com](https://console.anthropic.com)

### Backend

```bash
cd backend
cp .env.example .env           # Add your ANTHROPIC_API_KEY
uv sync                        # Install dependencies
docker compose up -d           # Start PostgreSQL
uv run uvicorn src.main:app --reload  # Start server at localhost:8000
```

### Frontend

```bash
cd frontend
npm install                    # Install dependencies
npm run dev                    # Start dev server at localhost:5173
```

### Tests

```bash
cd backend && uv run pytest    # Backend tests
cd frontend && npm test        # Frontend tests
```

---

## Project Structure

```
build-ai-agents/
├── backend/                   # FastAPI + Python 3.12
│   ├── src/
│   │   ├── main.py           # FastAPI app entry
│   │   ├── models/           # SQLAlchemy + Pydantic models
│   │   ├── services/         # Business logic + AI agent
│   │   └── routers/          # API endpoints
│   ├── tests/
│   └── pyproject.toml
├── frontend/                  # React 19 + TypeScript + Vite
│   ├── src/
│   └── package.json
├── docs/
│   ├── agent-arch/           # 7 docs: API → transformers → agents
│   ├── infra-arch/           # 13 docs: K8s → GKE → deployment
│   ├── SCOPE-V1.md           # V1 planning document
│   ├── SCOPE-V2.md           # V2 planning document
│   └── ARCHITECTURE.md       # System architecture vision
├── .claude/                   # Claude Code config
│   ├── settings.json         # Hooks, permissions
│   └── skills/               # 10 custom Claude Code skills
├── CLAUDE.md                  # Agent instructions (CLAUDE.md pattern)
├── docker-compose.yml         # PostgreSQL 16
└── README.md                  # This file
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| AI | Claude Agent SDK | Structured output, agentic workflows |
| Backend | FastAPI + Python 3.12 | API server, business logic |
| Frontend | React 19 + TypeScript + Vite | UI, patient dashboard |
| Database | PostgreSQL 16 | Patient records, consultations |
| Package Manager | uv | Fast Python dependency management |
| Coding Agent | Claude Code + CLAUDE.md | AI-first development workflow |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev environment setup, code style, and PR guidelines.

## License

[MIT](LICENSE)
