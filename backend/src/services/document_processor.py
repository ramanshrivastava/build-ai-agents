"""Structure-aware markdown parser and chunker for clinical guidelines."""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path

from src.models.rag import DocumentChunk


class Section:
    """A markdown section with heading hierarchy and body text."""

    def __init__(self, heading: str, level: int, body: str, path: list[str]) -> None:
        self.heading = heading
        self.level = level
        self.body = body
        self.path = (
            path  # e.g. ["Diabetes Management", "Pharmacologic Therapy", "Metformin"]
        )


def parse_markdown(text: str) -> list[Section]:
    """Parse markdown text into sections preserving heading hierarchy.

    Each section captures its heading, body text, and full path through
    the heading hierarchy (e.g. ["Chapter", "Section", "Subsection"]).
    """
    lines = text.split("\n")
    sections: list[Section] = []
    heading_stack: list[str] = []  # tracks current heading at each level
    current_heading = ""
    current_level = 0
    current_body_lines: list[str] = []

    def _flush() -> None:
        body = "\n".join(current_body_lines).strip()
        if body or current_heading:
            path = list(heading_stack)
            sections.append(
                Section(
                    heading=current_heading,
                    level=current_level,
                    body=body,
                    path=path,
                )
            )

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            _flush()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()

            # Update heading stack: trim to current level, then set
            heading_stack = heading_stack[: level - 1]
            while len(heading_stack) < level - 1:
                heading_stack.append("")
            heading_stack.append(heading)

            current_heading = heading
            current_level = level
            current_body_lines = []
        else:
            current_body_lines.append(line)

    _flush()
    return sections


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return len(text) // 4


def chunk_sections(
    sections: list[Section],
    *,
    max_tokens: int = 800,
    document_id: str = "",
    document_title: str = "",
    specialty: str = "",
    document_type: str = "clinical_guideline",
    conditions: list[str] | None = None,
    drugs: list[str] | None = None,
    publication_date: date | None = None,
) -> list[DocumentChunk]:
    """Convert parsed sections into DocumentChunks with section path prefix.

    Each chunk's text is prefixed with its section path for embedding context.
    Chunks that exceed max_tokens are split at paragraph boundaries.
    """
    if not document_id:
        document_id = str(uuid.uuid4())[:8]
    if publication_date is None:
        publication_date = date.today()

    raw_chunks: list[tuple[str, str]] = []  # (section_path, text)

    for section in sections:
        if not section.body:
            continue

        section_path = " > ".join(p for p in section.path if p)
        prefix = f"[{section_path}] " if section_path else ""
        full_text = prefix + section.body

        if _estimate_tokens(full_text) <= max_tokens:
            raw_chunks.append((section_path, full_text))
        else:
            # Split at paragraph boundaries
            paragraphs = re.split(r"\n\n+", section.body)
            current_parts: list[str] = []
            current_size = _estimate_tokens(prefix)

            for para in paragraphs:
                para_tokens = _estimate_tokens(para)
                if current_size + para_tokens > max_tokens and current_parts:
                    raw_chunks.append(
                        (section_path, prefix + "\n\n".join(current_parts))
                    )
                    current_parts = []
                    current_size = _estimate_tokens(prefix)
                current_parts.append(para)
                current_size += para_tokens

            if current_parts:
                raw_chunks.append((section_path, prefix + "\n\n".join(current_parts)))

    total = len(raw_chunks)
    return [
        DocumentChunk(
            text=text,
            document_id=document_id,
            document_title=document_title,
            section_path=section_path,
            specialty=specialty,
            document_type=document_type,
            conditions=conditions or [],
            drugs=drugs or [],
            publication_date=publication_date,
            chunk_index=idx,
            total_chunks=total,
        )
        for idx, (section_path, text) in enumerate(raw_chunks)
    ]


def parse_and_chunk_file(
    path: Path,
    *,
    max_tokens: int = 800,
    document_id: str = "",
    document_title: str = "",
    specialty: str = "",
    document_type: str = "clinical_guideline",
    conditions: list[str] | None = None,
    drugs: list[str] | None = None,
    publication_date: date | None = None,
) -> list[DocumentChunk]:
    """Convenience: parse a markdown file and return chunks."""
    text = path.read_text(encoding="utf-8")
    if not document_title:
        document_title = path.stem.replace("-", " ").replace("_", " ").title()
    if not document_id:
        document_id = path.stem
    sections = parse_markdown(text)
    return chunk_sections(
        sections,
        max_tokens=max_tokens,
        document_id=document_id,
        document_title=document_title,
        specialty=specialty,
        document_type=document_type,
        conditions=conditions,
        drugs=drugs,
        publication_date=publication_date,
    )
