"""Unit tests for agent tools."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

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


def _get_handler():
    """Get the raw async handler from the SdkMcpTool wrapper."""
    from src.agents.tools import search_clinical_guidelines

    return search_clinical_guidelines.handler


class TestSearchClinicalGuidelines:
    def test_tool_metadata(self) -> None:
        from src.agents.tools import search_clinical_guidelines

        assert search_clinical_guidelines.name == "search_clinical_guidelines"
        assert "clinical guidelines" in search_clinical_guidelines.description
        assert "query" in search_clinical_guidelines.input_schema

    @patch("src.agents.tools.async_search", new_callable=AsyncMock)
    async def test_returns_xml_content(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = [_make_result("Metformin renal dosing info")]
        handler = _get_handler()

        result = await handler({"query": "metformin renal dosing"})

        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        text = result["content"][0]["text"]
        assert "<clinical_guidelines>" in text
        assert "Metformin renal dosing info" in text

    @patch("src.agents.tools.async_search", new_callable=AsyncMock)
    async def test_passes_specialty_filter(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = []
        handler = _get_handler()

        await handler(
            {
                "query": "diabetes",
                "specialty": "endocrinology",
                "max_results": 3,
            }
        )

        mock_search.assert_called_once_with(
            query="diabetes", specialty="endocrinology", limit=3
        )

    @patch("src.agents.tools.async_search", new_callable=AsyncMock)
    async def test_handles_no_results(self, mock_search: AsyncMock) -> None:
        mock_search.return_value = []
        handler = _get_handler()

        result = await handler({"query": "unknown topic"})
        text = result["content"][0]["text"]
        assert "No relevant guidelines found" in text

    @patch("src.agents.tools.async_search", new_callable=AsyncMock)
    async def test_defaults_when_optional_params_missing(
        self, mock_search: AsyncMock
    ) -> None:
        mock_search.return_value = []
        handler = _get_handler()

        await handler({"query": "test"})

        mock_search.assert_called_once_with(query="test", specialty=None, limit=5)

    @patch("src.agents.tools.async_search", new_callable=AsyncMock)
    async def test_returns_error_content_on_exception(
        self, mock_search: AsyncMock
    ) -> None:
        mock_search.side_effect = ConnectionError("Qdrant connection refused")
        handler = _get_handler()

        result = await handler({"query": "metformin"})

        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "Error searching guidelines" in text
        assert "Qdrant connection refused" in text
