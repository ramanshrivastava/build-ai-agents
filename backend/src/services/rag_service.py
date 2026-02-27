"""RAG service: embedding, Qdrant storage, and vector search."""

from __future__ import annotations

import logging
import uuid

import httpx
from google import genai
from google.genai import types
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from src.config import settings
from src.models.rag import DocumentChunk, RetrievalResult

logger = logging.getLogger(__name__)

# --- Clients (lazy init) ---

_qdrant_client: QdrantClient | None = None
_async_qdrant_client: AsyncQdrantClient | None = None
_genai_client: genai.Client | None = None


def _qdrant_kwargs() -> dict:
    """Build kwargs for Qdrant client, including api_key if set."""
    kwargs: dict = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return kwargs


def get_qdrant_client() -> QdrantClient:
    """Get or create the Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(**_qdrant_kwargs())
    return _qdrant_client


def get_async_qdrant_client() -> AsyncQdrantClient:
    """Get or create the async Qdrant client (for use in async tool handlers)."""
    global _async_qdrant_client
    if _async_qdrant_client is None:
        _async_qdrant_client = AsyncQdrantClient(**_qdrant_kwargs())
    return _async_qdrant_client


def get_genai_client() -> genai.Client:
    """Get or create the Google GenAI client (Vertex AI via ADC).

    The same client instance exposes both sync (client.models) and async
    (client.aio.models) interfaces.
    """
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )
    return _genai_client


# --- Embedding ---

_VERTEX_PREDICT_URL = (
    "https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
    "/locations/{location}/publishers/google/models/{model}:predict"
)


def _vertex_embed_via_api_key(texts: list[str], task_type: str) -> list[list[float]]:
    """Call Vertex AI embedding endpoint directly using GCP API key."""
    url = _VERTEX_PREDICT_URL.format(
        location=settings.gcp_location,
        project=settings.gcp_project_id,
        model=settings.embedding_model,
    )
    body = {
        "instances": [{"content": t, "task_type": task_type} for t in texts],
        "parameters": {"outputDimensionality": settings.embedding_dimensions},
    }
    resp = httpx.post(
        url, params={"key": settings.google_api_key}, json=body, timeout=30
    )
    resp.raise_for_status()
    return [p["embeddings"]["values"] for p in resp.json()["predictions"]]


async def _async_vertex_embed_via_api_key(
    texts: list[str], task_type: str
) -> list[list[float]]:
    """Async version: call Vertex AI embedding endpoint using GCP API key."""
    url = _VERTEX_PREDICT_URL.format(
        location=settings.gcp_location,
        project=settings.gcp_project_id,
        model=settings.embedding_model,
    )
    body = {
        "instances": [{"content": t, "task_type": task_type} for t in texts],
        "parameters": {"outputDimensionality": settings.embedding_dimensions},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url, params={"key": settings.google_api_key}, json=body, timeout=30
        )
    resp.raise_for_status()
    return [p["embeddings"]["values"] for p in resp.json()["predictions"]]


def embed_text(text: str) -> list[float]:
    """Embed a single text string for query-time search."""
    logger.debug(
        "Embedding query (%d chars): %r",
        len(text),
        text[:100] + ("..." if len(text) > 100 else ""),
    )
    if settings.google_api_key:
        vectors = _vertex_embed_via_api_key([text], "RETRIEVAL_QUERY")
        vector = vectors[0]
    else:
        client = get_genai_client()
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=[text],
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimensions,
                task_type="RETRIEVAL_QUERY",
            ),
        )
        vector = list(response.embeddings[0].values)
    logger.debug("Embedded query -> %d-dim vector", len(vector))
    return vector


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts for document indexing."""
    logger.info(
        "Embedding batch of %d texts (model=%s, dims=%d)",
        len(texts),
        settings.embedding_model,
        settings.embedding_dimensions,
    )
    if settings.google_api_key:
        vectors = _vertex_embed_via_api_key(texts, "RETRIEVAL_DOCUMENT")
    else:
        client = get_genai_client()
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimensions,
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        vectors = [list(e.values) for e in response.embeddings]
    logger.info("Embedded %d texts -> %d vectors", len(texts), len(vectors))
    return vectors


# --- Qdrant Collection Management ---


def ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist."""
    client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )
        # Create payload indexes for filtering
        for field, schema_type in [
            ("document_id", PayloadSchemaType.KEYWORD),
            ("specialty", PayloadSchemaType.KEYWORD),
            ("document_type", PayloadSchemaType.KEYWORD),
            ("conditions", PayloadSchemaType.KEYWORD),
            ("drugs", PayloadSchemaType.KEYWORD),
        ]:
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=schema_type,
            )
        logger.info("Created Qdrant collection '%s'", settings.qdrant_collection)
    else:
        logger.info("Qdrant collection '%s' already exists", settings.qdrant_collection)


# --- Upsert ---


def upsert_chunks(chunks: list[DocumentChunk], vectors: list[list[float]]) -> None:
    """Upsert document chunks with their embedding vectors into Qdrant."""
    client = get_qdrant_client()
    points = [
        PointStruct(
            id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_DNS, f"{chunk.document_id}:{chunk.chunk_index}"
                )
            ),
            vector=vector,
            payload={
                "text": chunk.text,
                "document_id": chunk.document_id,
                "document_title": chunk.document_title,
                "section_path": chunk.section_path,
                "specialty": chunk.specialty,
                "document_type": chunk.document_type,
                "conditions": chunk.conditions,
                "drugs": chunk.drugs,
                "publication_date": chunk.publication_date.isoformat(),
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info("Upserted %d chunks into '%s'", len(points), settings.qdrant_collection)


# --- Search ---


def search(
    query: str,
    specialty: str | None = None,
    limit: int = 5,
) -> list[RetrievalResult]:
    """Embed query, search Qdrant, return scored results."""
    logger.info(
        "RAG search: query=%r specialty=%r limit=%d",
        query,
        specialty,
        limit,
    )
    query_vector = embed_text(query)

    # Build optional filter
    must_conditions = []
    if specialty:
        must_conditions.append(
            FieldCondition(key="specialty", match=MatchValue(value=specialty))
        )
    query_filter = Filter(must=must_conditions) if must_conditions else None

    logger.debug(
        "Searching Qdrant collection=%r filter=%s",
        settings.qdrant_collection,
        query_filter,
    )

    client = get_qdrant_client()
    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=query_filter,
        score_threshold=0.5,
        limit=limit,
        with_payload=True,
    )

    logger.info(
        "Qdrant returned %d points (threshold=0.5)",
        len(results.points),
    )

    retrieval_results = []
    for idx, point in enumerate(results.points):
        payload = point.payload
        chunk = DocumentChunk(
            text=payload["text"],
            document_id=payload["document_id"],
            document_title=payload["document_title"],
            section_path=payload["section_path"],
            specialty=payload["specialty"],
            document_type=payload["document_type"],
            conditions=payload["conditions"],
            drugs=payload["drugs"],
            publication_date=payload["publication_date"],
            chunk_index=payload["chunk_index"],
            total_chunks=payload["total_chunks"],
        )
        retrieval_results.append(
            RetrievalResult(chunk=chunk, score=point.score, source_id=idx + 1)
        )

    for r in retrieval_results:
        logger.debug(
            "  Result [%d] score=%.3f doc=%r section=%r",
            r.source_id,
            r.score,
            r.chunk.document_title,
            r.chunk.section_path,
        )

    return retrieval_results


# --- Async variants (for agent tool handlers — non-blocking) ---


async def async_embed_text(text: str) -> list[float]:
    """Embed a single text string asynchronously (non-blocking)."""
    logger.debug(
        "Async embedding query (%d chars): %r",
        len(text),
        text[:100] + ("..." if len(text) > 100 else ""),
    )
    if settings.google_api_key:
        vectors = await _async_vertex_embed_via_api_key([text], "RETRIEVAL_QUERY")
        vector = vectors[0]
    else:
        client = get_genai_client()
        response = await client.aio.models.embed_content(
            model=settings.embedding_model,
            contents=[text],
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dimensions,
                task_type="RETRIEVAL_QUERY",
            ),
        )
        vector = list(response.embeddings[0].values)
    logger.debug("Async embedded query -> %d-dim vector", len(vector))
    return vector


async def async_search(
    query: str,
    specialty: str | None = None,
    limit: int = 5,
) -> list[RetrievalResult]:
    """Embed query and search Qdrant asynchronously (non-blocking)."""
    logger.info(
        "Async RAG search: query=%r specialty=%r limit=%d",
        query,
        specialty,
        limit,
    )
    query_vector = await async_embed_text(query)

    # Build optional filter
    must_conditions = []
    if specialty:
        must_conditions.append(
            FieldCondition(key="specialty", match=MatchValue(value=specialty))
        )
    query_filter = Filter(must=must_conditions) if must_conditions else None

    logger.debug(
        "Async searching Qdrant collection=%r filter=%s",
        settings.qdrant_collection,
        query_filter,
    )

    client = get_async_qdrant_client()
    results = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=query_filter,
        score_threshold=0.5,
        limit=limit,
        with_payload=True,
    )

    logger.info(
        "Async Qdrant returned %d points (threshold=0.5)",
        len(results.points),
    )

    retrieval_results = []
    for idx, point in enumerate(results.points):
        payload = point.payload
        chunk = DocumentChunk(
            text=payload["text"],
            document_id=payload["document_id"],
            document_title=payload["document_title"],
            section_path=payload["section_path"],
            specialty=payload["specialty"],
            document_type=payload["document_type"],
            conditions=payload["conditions"],
            drugs=payload["drugs"],
            publication_date=payload["publication_date"],
            chunk_index=payload["chunk_index"],
            total_chunks=payload["total_chunks"],
        )
        retrieval_results.append(
            RetrievalResult(chunk=chunk, score=point.score, source_id=idx + 1)
        )

    for r in retrieval_results:
        logger.debug(
            "  Async result [%d] score=%.3f doc=%r section=%r",
            r.source_id,
            r.score,
            r.chunk.document_title,
            r.chunk.section_path,
        )

    return retrieval_results


def format_as_xml_sources(results: list[RetrievalResult]) -> str:
    """Format retrieval results as XML for agent consumption."""
    if not results:
        return (
            "<clinical_guidelines>No relevant guidelines found.</clinical_guidelines>"
        )

    lines = ["<clinical_guidelines>"]
    for r in results:
        lines.append(
            f'  <source id="{r.source_id}" '
            f'document="{r.chunk.document_title}" '
            f'section="{r.chunk.section_path}" '
            f'score="{r.score:.2f}">'
        )
        lines.append(f"    {r.chunk.text}")
        lines.append("  </source>")
    lines.append("</clinical_guidelines>")
    return "\n".join(lines)
