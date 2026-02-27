"""CLI script to ingest markdown clinical guidelines into Qdrant.

Usage:
    cd backend
    uv run python ../scripts/ingest_docs.py --directory ../data/guidelines/
    uv run python ../scripts/ingest_docs.py --file ../data/guidelines/diabetes-management.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add backend/src to path so imports work when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from src.services.document_processor import parse_and_chunk_file
from src.services.rag_service import embed_batch, ensure_collection, upsert_chunks

# Metadata mapping: filename stem -> metadata overrides
GUIDELINE_METADATA: dict[str, dict] = {
    "diabetes-management": {
        "specialty": "endocrinology",
        "conditions": ["type_2_diabetes"],
        "drugs": ["metformin", "insulin"],
    },
    "hypertension-guidelines": {
        "specialty": "cardiology",
        "conditions": ["hypertension"],
        "drugs": ["lisinopril", "amlodipine"],
    },
    "ckd-management": {
        "specialty": "nephrology",
        "conditions": ["chronic_kidney_disease"],
        "drugs": ["lisinopril", "metformin"],
    },
    "drug-interactions": {
        "specialty": "general",
        "conditions": [],
        "drugs": ["metformin", "lisinopril", "atorvastatin", "amlodipine"],
    },
    "chf-afib-management": {
        "specialty": "cardiology",
        "conditions": ["heart_failure", "atrial_fibrillation"],
        "drugs": ["metoprolol", "furosemide", "apixaban"],
    },
}


def ingest_file(path: Path, collection: str | None = None) -> int:
    """Ingest a single markdown file. Returns number of chunks upserted."""
    meta = GUIDELINE_METADATA.get(path.stem, {})
    chunks = parse_and_chunk_file(
        path,
        specialty=meta.get("specialty", "general"),
        conditions=meta.get("conditions"),
        drugs=meta.get("drugs"),
    )
    if not chunks:
        print(f"  Skipped {path.name} (no chunks)")
        return 0

    print(f"  Chunked {path.name} -> {len(chunks)} chunks")

    texts = [c.text for c in chunks]
    print(f"  Embedding {len(texts)} chunks...")
    vectors = embed_batch(texts)

    print(f"  Upserting to Qdrant...")
    upsert_chunks(chunks, vectors)

    return len(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest clinical guidelines into Qdrant")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--directory", type=Path, help="Directory of markdown files to ingest")
    group.add_argument("--file", type=Path, help="Single markdown file to ingest")
    parser.add_argument("--collection", type=str, default=None, help="Qdrant collection name override")
    args = parser.parse_args()

    # Ensure collection exists
    print("Ensuring Qdrant collection exists...")
    ensure_collection()

    total_chunks = 0
    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        print(f"Ingesting {args.file.name}...")
        total_chunks = ingest_file(args.file, args.collection)
    else:
        if not args.directory.exists():
            print(f"Error: Directory not found: {args.directory}")
            sys.exit(1)
        md_files = sorted(args.directory.glob("*.md"))
        if not md_files:
            print(f"No .md files found in {args.directory}")
            sys.exit(1)
        print(f"Found {len(md_files)} markdown files")
        for f in md_files:
            print(f"\nIngesting {f.name}...")
            total_chunks += ingest_file(f, args.collection)

    print(f"\nDone! Ingested {total_chunks} total chunks.")


if __name__ == "__main__":
    main()
