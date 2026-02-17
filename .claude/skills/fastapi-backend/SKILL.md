---
name: fastapi-backend
description: FastAPI backend patterns for AI Doctor Assistant
---

# FastAPI Backend Development Skill

## Tech Stack
- FastAPI with async/await patterns
- Pydantic v2 for validation
- SQLAlchemy 2.0 with async sessions
- aiosqlite for SQLite async support
- uv for dependency management (NOT pip)
- ruff for formatting and linting
- pytest-asyncio for testing

## Key Patterns

### Pydantic v2
```python
# Correct (v2)
obj = MyModel.model_validate(data)
json_str = obj.model_dump_json()

# Wrong (v1 - don't use)
# obj = MyModel.parse_obj(data)
```

### Async Database Sessions
```python
from src.database import get_session
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/items")
async def get_items(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Item))
    return result.scalars().all()
```

### Error Handling
```python
from fastapi import HTTPException

if not item:
    raise HTTPException(status_code=404, detail="Item not found")
```

## File Structure
```
src/
├── __init__.py
├── main.py              # FastAPI app entry
├── config.py            # Settings from env vars
├── models/              # Pydantic models
├── services/            # Business logic
├── agents/              # Claude Agent SDK agents
│   ├── briefing_agent.py
│   ├── tools.py         # @tool definitions
│   └── hooks.py         # Langfuse hooks
├── routers/             # API routes
└── database.py          # SQLAlchemy setup
```

## Running Commands
```bash
# Start server
uv run uvicorn src.main:app --reload

# Run tests
uv run pytest

# Format code
uv run ruff format .

# Lint code
uv run ruff check . --fix
```

## Code Style
- Use `from __future__ import annotations` for forward refs
- Type hints on ALL function signatures
- Use `async def` for I/O-bound operations
- Organize routers by domain (patients, briefings)
