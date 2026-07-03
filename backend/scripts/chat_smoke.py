"""Stage-0 smoke test for the unified patient-chat design.

Proves three SDK behaviors end-to-end against the live LiteLLM/Gemini proxy
before we build the feature on top of them:

  1. RESUME  — a conversation started by one ClaudeSDKClient can be continued
               by a *fresh* client via ClaudeAgentOptions(resume=session_id).
               Transcripts live client-side (~/.claude/projects/, keyed by cwd),
               so this works regardless of which model serves the tokens.
  2. SKILL   — a filesystem skill (.claude/skills/briefing/SKILL.md) loads via
               setting_sources=["project"] + cwd, and "/briefing" invokes it.
  3. QUEUE   — an in-process SDK MCP tool handler runs inside *this* process's
               event loop, so it can feed an asyncio.Queue that a concurrent
               consumer (our future SSE generator) drains mid-stream.

Run from backend/ with the nested-CLI env stripped and the proxy vars set:

  env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_SESSION_ID \
      ANTHROPIC_BASE_URL=http://localhost:4000 AI_MODEL=gemini-3.1-pro-preview \
      uv run python scripts/chat_smoke.py
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    CLIConnectionError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

# Make `src` importable when run as `python scripts/chat_smoke.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.briefing_agent import _proxy_env  # noqa: E402
from src.config import settings  # noqa: E402

TURN_TIMEOUT = 180  # seconds per model turn — Gemini via proxy can be slow

SKILL_MARKER = "PINEAPPLE-PROTOCOL-7"
SKILL_MD = f"""---
name: briefing
description: Generate a pre-consultation patient briefing. Use when the
  physician asks for a briefing or pre-consultation summary.
---
# Briefing (smoke-test stub)

This is a smoke-test stub. When this skill is invoked, begin your reply with
the exact phrase: {SKILL_MARKER}
"""


def _base_options(**overrides: Any) -> ClaudeAgentOptions:
    """Minimal options mirroring what the chat agent will use."""
    defaults: dict[str, Any] = {
        "model": settings.ai_model,
        "env": _proxy_env(),
        "permission_mode": "bypassPermissions",
        "max_turns": 4,
    }
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


async def _run_turn(
    client: ClaudeSDKClient, prompt: str
) -> tuple[str | None, str | None, str]:
    """Send one prompt and drain the response.

    Returns (init_session_id, result_session_id, assistant_text).
    """
    await client.query(prompt)
    init_sid: str | None = None
    result_sid: str | None = None
    text_parts: list[str] = []
    try:
        async for message in client.receive_response():
            if isinstance(message, SystemMessage) and message.subtype == "init":
                init_sid = message.data.get("session_id")
            elif isinstance(message, AssistantMessage):
                text_parts.extend(
                    block.text
                    for block in message.content
                    if isinstance(block, TextBlock)
                )
            elif isinstance(message, ResultMessage):
                result_sid = message.session_id
                if message.is_error:
                    raise RuntimeError(f"turn errored: {message.result}")
    except BaseExceptionGroup as eg:
        # Mirror the agent code: shutdown can wrap CLIConnectionError in a
        # task-group ExceptionGroup after a valid result — safe to ignore then.
        cli_errors = eg.subgroup(CLIConnectionError)
        if not (cli_errors and result_sid is not None):
            raise
    return init_sid, result_sid, "".join(text_parts)


async def test_resume(cwd: Path) -> None:
    """Turn 1 (client A) states a fact; turn 2 (fresh client B) must recall it."""
    opts = _base_options(cwd=str(cwd))
    async with ClaudeSDKClient(opts) as client_a:
        init_sid, result_sid, _ = await asyncio.wait_for(
            _run_turn(client_a, "My name is Maria. Remember it and reply OK."),
            TURN_TIMEOUT,
        )
    assert result_sid, "no session_id on ResultMessage"
    print(f"    turn 1 session_id: init={init_sid} result={result_sid}")

    # Fresh client, same cwd (resume lookup is keyed by cwd), resume= the id.
    opts2 = _base_options(cwd=str(cwd), resume=result_sid)
    async with ClaudeSDKClient(opts2) as client_b:
        _, _, text = await asyncio.wait_for(
            _run_turn(client_b, "What is my name? Reply with just the name."),
            TURN_TIMEOUT,
        )
    print(f"    turn 2 reply: {text!r}")
    assert "maria" in text.lower(), f"resume failed — reply was {text!r}"


async def test_skill_slash(cwd: Path) -> bool:
    """Send '/briefing'; return True if slash invocation triggered the skill.

    Falls back to a natural-language trigger and reports which one worked.
    """
    skill_dir = cwd / ".claude" / "skills" / "briefing"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD)

    opts = _base_options(
        cwd=str(cwd),
        setting_sources=["project"],
        allowed_tools=["Skill"],
    )
    async with ClaudeSDKClient(opts) as client:
        _, _, text = await asyncio.wait_for(
            _run_turn(client, "/briefing"), TURN_TIMEOUT
        )
    print(f"    /briefing reply: {text[:200]!r}")
    if SKILL_MARKER in text:
        return True

    # Fallback: natural-language trigger matching the skill description.
    async with ClaudeSDKClient(opts) as client:
        _, _, text = await asyncio.wait_for(
            _run_turn(
                client, "Generate the pre-consultation briefing for this patient now."
            ),
            TURN_TIMEOUT,
        )
    print(f"    natural-language reply: {text[:200]!r}")
    assert SKILL_MARKER in text, "skill did not fire via slash OR natural language"
    return False


async def test_queue_interception(cwd: Path) -> None:
    """An in-process tool handler must feed an asyncio.Queue we drain concurrently."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    @tool(
        "publish_test",
        "Publish a message to the physician's dashboard.",
        {"message": str},
    )
    async def publish_test(args: dict[str, Any]) -> dict[str, Any]:
        await queue.put(args)
        return {"content": [{"type": "text", "text": "published"}]}

    publisher = create_sdk_mcp_server(name="publisher", tools=[publish_test])
    opts = _base_options(
        cwd=str(cwd),
        mcp_servers={"publisher": publisher},
        allowed_tools=["mcp__publisher__publish_test"],
    )

    async def drive() -> str:
        async with ClaudeSDKClient(opts) as client:
            _, _, text = await _run_turn(
                client,
                "Call the publish_test tool with message='hello' and then say done.",
            )
            return text

    task = asyncio.create_task(drive())
    try:
        # Drain the queue while the turn is still running — proving mid-stream
        # fan-in.
        published = await asyncio.wait_for(queue.get(), TURN_TIMEOUT)
        mid_stream = not task.done()
        text = await asyncio.wait_for(task, TURN_TIMEOUT)
    finally:
        # Don't leave the driver (and its SDK subprocess) running if a wait
        # above timed out.
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    print(f"    tool args received: {published} (mid-stream={mid_stream})")
    print(f"    final reply: {text[:120]!r}")
    assert published.get("message") == "hello"
    assert mid_stream, "queue item only arrived after the turn finished"


async def main() -> int:
    print(
        f"model={settings.ai_model} base_url={settings.anthropic_base_url or '(real Anthropic)'}"
    )
    workdir = Path(tempfile.mkdtemp(prefix="chat_smoke_"))
    print(f"agent cwd: {workdir}")
    failures = 0
    try:
        for name, coro in (
            ("resume", test_resume(workdir)),
            ("skill", test_skill_slash(workdir)),
            ("queue", test_queue_interception(workdir)),
        ):
            print(f"[{name}]")
            try:
                result = await coro
                if name == "skill":
                    mode = "slash /briefing" if result else "NATURAL-LANGUAGE FALLBACK"
                    print(f"  PASS ({mode})")
                else:
                    print("  PASS")
            except Exception as exc:  # noqa: BLE001 — smoke test reports and continues
                failures += 1
                print(f"  FAIL: {exc!r}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    print("ALL PASS" if failures == 0 else f"{failures} FAILURE(S)")
    return failures


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
