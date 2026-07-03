"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.logging import RichHandler

from src.config import settings
from src.database import engine
from src.routers.briefings import router as briefings_router
from src.routers.chat import router as chat_router
from src.routers.patients import router as patients_router

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(message)s",
    datefmt="%H:%M:%S",
    handlers=[RichHandler(rich_tracebacks=True, markup=False)],
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# Our app loggers: show DEBUG when debug=True, keep third-party libs at INFO
if settings.debug:
    for name in ("src.agents", "src.services", "src.routers"):
        logging.getLogger(name).setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Surface the effective LLM routing at boot so it's obvious whether the
    # agent is hitting Anthropic directly or going through a translation proxy
    # (e.g. LiteLLM -> Vertex Gemini).
    logger.info(
        "LLM routing: model=%s via %s",
        settings.ai_model,
        settings.anthropic_base_url or "direct (Anthropic)",
    )
    if settings.anthropic_base_url and settings.ai_model.startswith("claude"):
        logger.warning(
            "ANTHROPIC_BASE_URL is set (proxy mode) but AI_MODEL=%s looks like a "
            "Claude id — set AI_MODEL to the proxy model name (e.g. gemini-2.5-pro) "
            "or the proxy will receive a model it doesn't know.",
            settings.ai_model,
        )
    yield
    await engine.dispose()


app = FastAPI(
    title="Build AI Agents",
    description="Pre-consultation patient briefing system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_credentials=True,
    allow_headers=["*"],
)

app.include_router(patients_router)
app.include_router(briefings_router)
app.include_router(chat_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
