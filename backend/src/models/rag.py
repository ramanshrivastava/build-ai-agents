"""Pydantic models for RAG: document chunks and retrieval results."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DocumentChunk(BaseModel):
    """A chunk of a clinical guideline document with metadata for vector storage."""

    text: str
    document_id: str
    document_title: str
    section_path: str
    specialty: str
    document_type: str
    conditions: list[str]
    drugs: list[str]
    publication_date: date
    chunk_index: int
    total_chunks: int


class RetrievalResult(BaseModel):
    """A search result from Qdrant with similarity score."""

    chunk: DocumentChunk
    score: float
    source_id: int
