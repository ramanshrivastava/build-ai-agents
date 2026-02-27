"""Agent tools for clinical guideline search."""

from __future__ import annotations

import logging

from claude_agent_sdk import tool

from src.services.rag_service import async_search, format_as_xml_sources

logger = logging.getLogger(__name__)


@tool(
    "search_clinical_guidelines",
    "Search clinical guidelines, drug interactions, and protocols. "
    "Returns relevant passages with source citations. Use this tool to find "
    "evidence-based recommendations for patient conditions and medications.",
    {
        "query": str,
        "specialty": str,
        "max_results": int,
    },
)
async def search_clinical_guidelines(args: dict) -> dict:
    """Search Qdrant for relevant clinical guideline chunks."""
    query_text = args.get("query", "")
    specialty = args.get("specialty")
    max_results = args.get("max_results", 5)

    logger.info(
        "Tool called: search_clinical_guidelines(query=%r, specialty=%r, max_results=%d)",
        query_text,
        specialty,
        max_results,
    )

    try:
        results = await async_search(
            query=query_text,
            specialty=specialty if specialty else None,
            limit=max_results,
        )
    except Exception as e:
        logger.exception("Tool search_clinical_guidelines failed")
        return {
            "content": [{"type": "text", "text": f"Error searching guidelines: {e}"}],
            "isError": True,
        }

    logger.info("Tool result: %d chunks returned", len(results))
    for r in results:
        logger.info(
            "  [%d] score=%.3f doc=%r section=%r text=%r",
            r.source_id,
            r.score,
            r.chunk.document_title,
            r.chunk.section_path,
            r.chunk.text[:100] + ("..." if len(r.chunk.text) > 100 else ""),
        )

    formatted = format_as_xml_sources(results)
    logger.debug("Tool XML response (%d chars):\n%s", len(formatted), formatted)
    return {"content": [{"type": "text", "text": formatted}]}
