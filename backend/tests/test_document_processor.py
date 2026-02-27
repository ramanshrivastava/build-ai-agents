"""Unit tests for document_processor: markdown parsing and chunking."""

from __future__ import annotations

from datetime import date

from src.services.document_processor import (
    Section,
    chunk_sections,
    parse_markdown,
)

SAMPLE_MD = """\
# Diabetes Management

Overview of diabetes management guidelines.

## Pharmacologic Therapy

### Metformin

Metformin is the preferred initial agent for type 2 diabetes.
Dose adjustment required when eGFR falls below 45 mL/min.

### Insulin

Insulin therapy should be considered when HbA1c targets are not met.

## Monitoring

Regular HbA1c monitoring every 3 months.
"""


class TestParseMarkdown:
    def test_extracts_correct_sections(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        headings = [s.heading for s in sections]
        assert "Diabetes Management" in headings
        assert "Metformin" in headings
        assert "Insulin" in headings
        assert "Monitoring" in headings

    def test_section_paths(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        by_heading = {s.heading: s for s in sections}

        metformin = by_heading["Metformin"]
        assert metformin.path == [
            "Diabetes Management",
            "Pharmacologic Therapy",
            "Metformin",
        ]

        insulin = by_heading["Insulin"]
        assert insulin.path == [
            "Diabetes Management",
            "Pharmacologic Therapy",
            "Insulin",
        ]

        monitoring = by_heading["Monitoring"]
        assert monitoring.path == ["Diabetes Management", "Monitoring"]

    def test_section_levels(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        by_heading = {s.heading: s for s in sections}

        assert by_heading["Diabetes Management"].level == 1
        assert by_heading["Pharmacologic Therapy"].level == 2
        assert by_heading["Metformin"].level == 3

    def test_body_text_captured(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        by_heading = {s.heading: s for s in sections}
        assert "preferred initial agent" in by_heading["Metformin"].body

    def test_empty_body_sections(self) -> None:
        md = "# Title\n## Empty Section\n## Has Body\nSome text."
        sections = parse_markdown(md)
        bodies = {s.heading: s.body for s in sections}
        assert bodies["Empty Section"] == ""
        assert bodies["Has Body"] == "Some text."


class TestChunkSections:
    def test_basic_chunking(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        chunks = chunk_sections(
            sections,
            document_id="test-doc",
            document_title="Test",
            specialty="endocrinology",
            publication_date=date(2025, 1, 1),
        )
        # Should produce chunks for sections with body text
        assert len(chunks) > 0
        assert all(c.document_id == "test-doc" for c in chunks)
        assert all(c.specialty == "endocrinology" for c in chunks)

    def test_section_path_in_chunk_text(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        chunks = chunk_sections(sections, document_id="test")
        metformin_chunks = [c for c in chunks if "Metformin" in c.section_path]
        assert len(metformin_chunks) > 0
        for chunk in metformin_chunks:
            assert chunk.text.startswith("[")
            assert "Metformin" in chunk.text

    def test_chunk_index_and_total(self) -> None:
        sections = parse_markdown(SAMPLE_MD)
        chunks = chunk_sections(sections, document_id="test")
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == total

    def test_max_token_limit_splits(self) -> None:
        """Long sections get split at paragraph boundaries."""
        long_body = "\n\n".join(
            f"Paragraph {i} with enough text to matter." for i in range(50)
        )
        sections = [Section(heading="Long", level=1, body=long_body, path=["Long"])]
        chunks = chunk_sections(sections, max_tokens=100, document_id="test")
        assert len(chunks) > 1
        for chunk in chunks:
            # Rough check: no chunk should be wildly over the limit
            # (4 chars/token estimate, 100 tokens = ~400 chars, with some slack)
            assert len(chunk.text) < 800  # generous upper bound

    def test_empty_sections_skipped(self) -> None:
        sections = [
            Section(heading="Empty", level=1, body="", path=["Empty"]),
            Section(heading="HasBody", level=1, body="Content here.", path=["HasBody"]),
        ]
        chunks = chunk_sections(sections, document_id="test")
        assert len(chunks) == 1
        assert "Content here." in chunks[0].text

    def test_metadata_propagated(self) -> None:
        sections = parse_markdown("# Test\nBody text.")
        chunks = chunk_sections(
            sections,
            document_id="doc-1",
            document_title="My Doc",
            specialty="cardiology",
            document_type="protocol",
            conditions=["CHF"],
            drugs=["metoprolol"],
            publication_date=date(2025, 6, 1),
        )
        assert len(chunks) == 1
        c = chunks[0]
        assert c.document_title == "My Doc"
        assert c.conditions == ["CHF"]
        assert c.drugs == ["metoprolol"]
        assert c.publication_date == date(2025, 6, 1)
