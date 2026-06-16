"""Isolation tests for the standalone FastMCP server.

Uses FastMCP's in-memory transport (`Client(mcp)`) so the tool is exercised exactly as
it would be over HTTP, but with no network, no agent, and `async_search` mocked (no live
Qdrant/Vertex). This is the "test the MCP server on its own" path.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from fastmcp import Client

from mcp_server.server import mcp
from src.models.rag import DocumentChunk, RetrievalResult


def _make_result(text: str = "Test content", source_id: int = 1) -> RetrievalResult:
    chunk = DocumentChunk(
        text=text,
        document_id="doc-1",
        document_title="Test Guideline",
        section_path="Section > Sub",
        specialty="endocrinology",
        document_type="clinical_guideline",
        conditions=["diabetes"],
        drugs=["metformin"],
        publication_date=date(2025, 1, 1),
        chunk_index=0,
        total_chunks=1,
    )
    return RetrievalResult(chunk=chunk, score=0.85, source_id=source_id)


async def test_tool_is_discoverable() -> None:
    """The server advertises search_clinical_guidelines via tools/list."""
    async with Client(mcp) as client:
        tools = await client.list_tools()

    names = {t.name for t in tools}
    assert "search_clinical_guidelines" in names


@patch("mcp_server.server.async_search", new_callable=AsyncMock)
async def test_call_returns_xml_sources(mock_search: AsyncMock) -> None:
    """Calling the tool returns the formatted XML from the search results."""
    mock_search.return_value = [_make_result("Metformin renal dosing info")]

    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_clinical_guidelines", {"query": "metformin renal dosing"}
        )

    text = result.content[0].text
    assert "<clinical_guidelines>" in text
    assert "Metformin renal dosing info" in text


@patch("mcp_server.server.async_search", new_callable=AsyncMock)
async def test_call_passes_specialty_and_limit(mock_search: AsyncMock) -> None:
    """Optional args are forwarded to async_search; empty specialty becomes None."""
    mock_search.return_value = []

    async with Client(mcp) as client:
        await client.call_tool(
            "search_clinical_guidelines",
            {"query": "diabetes", "specialty": "endocrinology", "max_results": 3},
        )

    mock_search.assert_called_once_with(
        query="diabetes", specialty="endocrinology", limit=3
    )


@patch("mcp_server.server.async_search", new_callable=AsyncMock)
async def test_empty_specialty_maps_to_none(mock_search: AsyncMock) -> None:
    """A blank specialty string is normalized to None (no filter)."""
    mock_search.return_value = []

    async with Client(mcp) as client:
        await client.call_tool("search_clinical_guidelines", {"query": "test"})

    mock_search.assert_called_once_with(query="test", specialty=None, limit=5)
