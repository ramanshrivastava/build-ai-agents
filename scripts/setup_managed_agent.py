"""Create Claude Managed Agents resources for the AI Doctor example.

Usage:
    cd backend
    uv run python ../scripts/setup_managed_agent.py
"""

from __future__ import annotations

import asyncio
import sys

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from anthropic import AsyncAnthropic

from src.config import settings
from src.database import engine
from src.models.orm import Base
from src.services.managed_briefing_service import MANAGED_SYSTEM_PROMPT, TOOL_SCHEMA


async def ensure_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY must be set before creating resources.")

    await ensure_tables()

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    environment = await client.beta.environments.create(
        name="Build AI Agents - AI Doctor",
        description="Cloud environment for the course Managed Agents example.",
        config={"type": "cloud"},
        metadata={"course": "build-ai-agents"},
    )
    agent = await client.beta.agents.create(
        name="AI Doctor Briefing Agent",
        description="Synthetic patient briefing agent for the Build AI Agents course.",
        model=settings.ai_model,
        system=MANAGED_SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        metadata={"course": "build-ai-agents"},
    )

    print("Claude Managed Agents resources created.")
    print()
    print("Add these values to backend/.env:")
    print(f"MANAGED_AGENT_ID={agent.id}")
    print(f"MANAGED_ENVIRONMENT_ID={environment.id}")


if __name__ == "__main__":
    asyncio.run(main())
