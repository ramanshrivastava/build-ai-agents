# Contributing

Thanks for your interest in contributing to Build AI Agents!

## Dev Environment Setup

### Backend

```bash
cd backend
uv sync          # Install Python dependencies
uv run pytest    # Run tests
uv run uvicorn src.main:app --reload  # Start dev server
```

### Frontend

```bash
cd frontend
npm install      # Install Node dependencies
npm test         # Run tests
npm run dev      # Start dev server
```

### Database

```bash
docker compose up -d  # Start PostgreSQL 16
```

## Code Style

- **Python:** Formatted with `ruff` — runs automatically via Claude Code hooks
- **TypeScript:** ESLint + Prettier
- Small, focused functions with early returns
- Type hints on all Python functions
- Functional components + hooks only (no class components)

## Branch Naming

- Features: `feat/<name>`
- Bug fixes: `fix/<name>`

## Pull Requests

1. Fork the repo and create your branch from `main`
2. Run tests before submitting (`uv run pytest` + `npm test`)
3. Write a clear PR description explaining what and why
4. Keep PRs focused — one feature or fix per PR

## Questions?

Open an issue if something is unclear or you need guidance on where to contribute.
