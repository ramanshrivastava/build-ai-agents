"""Unit tests for rag_service: embedding, storage, search, XML formatting."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient

from src.models.rag import DocumentChunk, RetrievalResult
from src.services import rag_service


# --- Fixtures ---


def _make_chunk(
    text: str = "Sample chunk text",
    document_id: str = "doc-1",
    chunk_index: int = 0,
    total_chunks: int = 1,
    specialty: str = "endocrinology",
    section_path: str = "Section > Subsection",
) -> DocumentChunk:
    return DocumentChunk(
        text=text,
        document_id=document_id,
        document_title="Test Document",
        section_path=section_path,
        specialty=specialty,
        document_type="clinical_guideline",
        conditions=["diabetes"],
        drugs=["metformin"],
        publication_date=date(2025, 1, 1),
        chunk_index=chunk_index,
        total_chunks=total_chunks,
    )


def _fake_embedding(dim: int = 768) -> list[float]:
    """Deterministic fake embedding vector."""
    return [0.1] * dim


def _mock_embed_response(num_texts: int = 1, dim: int = 768) -> MagicMock:
    """Create a mock response matching google.genai embed_content response."""
    mock_resp = MagicMock()
    embeddings = []
    for _ in range(num_texts):
        emb = MagicMock()
        emb.values = _fake_embedding(dim)
        embeddings.append(emb)
    mock_resp.embeddings = embeddings
    return mock_resp


@pytest.fixture
def in_memory_qdrant(monkeypatch: pytest.MonkeyPatch) -> QdrantClient:
    """Use in-memory Qdrant for tests."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(rag_service, "_qdrant_client", client)
    monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: client)
    return client


@pytest.fixture
def mock_genai(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock the GenAI client so no real API calls are made."""
    mock_client = MagicMock()
    monkeypatch.setattr(rag_service, "_genai_client", mock_client)
    monkeypatch.setattr(rag_service, "get_genai_client", lambda: mock_client)
    # Force SDK path (not API key httpx path) so mocks are used
    monkeypatch.setattr("src.config.settings.google_api_key", "")
    return mock_client


# --- Embedding Tests ---


class TestEmbedText:
    def test_returns_vector(self, mock_genai: MagicMock) -> None:
        mock_genai.models.embed_content.return_value = _mock_embed_response(1)
        result = rag_service.embed_text("test query")
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_calls_with_query_task_type(self, mock_genai: MagicMock) -> None:
        mock_genai.models.embed_content.return_value = _mock_embed_response(1)
        rag_service.embed_text("test query")
        call_kwargs = mock_genai.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_QUERY"


class TestEmbedBatch:
    def test_returns_multiple_vectors(self, mock_genai: MagicMock) -> None:
        mock_genai.models.embed_content.return_value = _mock_embed_response(3)
        result = rag_service.embed_batch(["a", "b", "c"])
        assert len(result) == 3
        assert all(len(v) == 768 for v in result)

    def test_calls_with_document_task_type(self, mock_genai: MagicMock) -> None:
        mock_genai.models.embed_content.return_value = _mock_embed_response(2)
        rag_service.embed_batch(["a", "b"])
        call_kwargs = mock_genai.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_DOCUMENT"


# --- Collection Management Tests ---


class TestEnsureCollection:
    def test_creates_collection(self, in_memory_qdrant: QdrantClient) -> None:
        rag_service.ensure_collection()
        collections = [c.name for c in in_memory_qdrant.get_collections().collections]
        assert "clinical_guidelines" in collections

    def test_idempotent(self, in_memory_qdrant: QdrantClient) -> None:
        rag_service.ensure_collection()
        rag_service.ensure_collection()  # should not raise
        collections = [c.name for c in in_memory_qdrant.get_collections().collections]
        assert collections.count("clinical_guidelines") == 1


# --- Upsert Tests ---


class TestUpsertChunks:
    def test_upsert_and_count(self, in_memory_qdrant: QdrantClient) -> None:
        rag_service.ensure_collection()
        chunks = [_make_chunk(chunk_index=i, total_chunks=3) for i in range(3)]
        vectors = [_fake_embedding() for _ in chunks]
        rag_service.upsert_chunks(chunks, vectors)

        info = in_memory_qdrant.get_collection("clinical_guidelines")
        assert info.points_count == 3

    def test_upsert_idempotent(self, in_memory_qdrant: QdrantClient) -> None:
        """Same document_id + chunk_index → same UUID5 → no duplicates."""
        rag_service.ensure_collection()
        chunk = _make_chunk()
        vector = _fake_embedding()
        rag_service.upsert_chunks([chunk], [vector])
        rag_service.upsert_chunks([chunk], [vector])  # same data

        info = in_memory_qdrant.get_collection("clinical_guidelines")
        assert info.points_count == 1

    def test_payload_fields_stored(self, in_memory_qdrant: QdrantClient) -> None:
        rag_service.ensure_collection()
        chunk = _make_chunk(text="Metformin renal dosing info")
        rag_service.upsert_chunks([chunk], [_fake_embedding()])

        # Scroll to get points
        points, _ = in_memory_qdrant.scroll(
            collection_name="clinical_guidelines", limit=1, with_payload=True
        )
        payload = points[0].payload
        assert payload["text"] == "Metformin renal dosing info"
        assert payload["document_id"] == "doc-1"
        assert payload["specialty"] == "endocrinology"
        assert payload["conditions"] == ["diabetes"]


# --- Search Tests ---


class TestSearch:
    def test_returns_results(
        self, in_memory_qdrant: QdrantClient, mock_genai: MagicMock
    ) -> None:
        # Setup: create collection, upsert a chunk
        rag_service.ensure_collection()
        chunk = _make_chunk(text="Metformin dose adjustment for renal impairment")
        rag_service.upsert_chunks([chunk], [_fake_embedding()])

        # Mock the query embedding to return the same vector (perfect match)
        mock_genai.models.embed_content.return_value = _mock_embed_response(1)

        results = rag_service.search("metformin renal dosing")
        assert len(results) == 1
        assert isinstance(results[0], RetrievalResult)
        assert results[0].source_id == 1
        assert results[0].score > 0

    def test_specialty_filter(
        self, in_memory_qdrant: QdrantClient, mock_genai: MagicMock
    ) -> None:
        rag_service.ensure_collection()
        endo_chunk = _make_chunk(
            text="Diabetes chunk", specialty="endocrinology", document_id="d1"
        )
        cardio_chunk = _make_chunk(
            text="Heart chunk", specialty="cardiology", document_id="d2"
        )
        rag_service.upsert_chunks(
            [endo_chunk, cardio_chunk],
            [_fake_embedding(), _fake_embedding()],
        )

        mock_genai.models.embed_content.return_value = _mock_embed_response(1)
        results = rag_service.search("diabetes", specialty="endocrinology")
        specialties = {r.chunk.specialty for r in results}
        assert "cardiology" not in specialties


# --- XML Formatting Tests ---


class TestFormatAsXmlSources:
    def test_formats_results(self) -> None:
        chunk = _make_chunk(text="Metformin reduces HbA1c.")
        results = [RetrievalResult(chunk=chunk, score=0.89, source_id=1)]
        xml = rag_service.format_as_xml_sources(results)
        assert "<clinical_guidelines>" in xml
        assert 'id="1"' in xml
        assert 'document="Test Document"' in xml
        assert "Metformin reduces HbA1c." in xml
        assert "</clinical_guidelines>" in xml

    def test_empty_results(self) -> None:
        xml = rag_service.format_as_xml_sources([])
        assert "No relevant guidelines found" in xml

    def test_multiple_sources(self) -> None:
        chunks = [
            _make_chunk(text=f"Chunk {i}", chunk_index=i, total_chunks=3)
            for i in range(3)
        ]
        results = [
            RetrievalResult(chunk=c, score=0.9 - i * 0.1, source_id=i + 1)
            for i, c in enumerate(chunks)
        ]
        xml = rag_service.format_as_xml_sources(results)
        assert xml.count("<source ") == 3
        assert 'id="1"' in xml
        assert 'id="3"' in xml
