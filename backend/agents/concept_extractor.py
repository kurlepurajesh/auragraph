"""
Local Concept Extractor — AuraGraph
Extracts topic nodes and edges from generated Markdown notes.

Primary path: LLM-powered knowledge graph via graph_builder module.
Fallback: deterministic extraction from Contents section / headings.
"""
import re
from typing import Any


def _normalize_id(label: str) -> str:
    """Convert a topic label to a lowercase underscore-separated id."""
    return re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')


def extract_topics_from_contents(note_text: str) -> dict[str, Any]:
    """
    Deterministic fallback: parse the "Contents" section or ## headings
    of a Markdown note and return a graph dict.

    Used when LLM graph building is unavailable.
    """
    topics: list[str] = []

    # ── 1. Try to find a "Contents" / "Table of Contents" section ────────
    contents_match = re.search(
        r'(?:^|\n)#{0,3}\s*(?:table\s+of\s+)?contents\s*\n(.*?)(?=\n#{1,3}\s|\Z)',
        note_text, re.IGNORECASE | re.DOTALL,
    )
    if contents_match:
        block = contents_match.group(1)
        entries = re.findall(r'^\s*\d+[\.\)]\s*(.+)$', block, re.MULTILINE)
        topics = [e.strip().rstrip('.') for e in entries if e.strip()]

    # ── 2. Fallback: extract ## headings as topics ───────────────────────
    if not topics:
        headings = re.findall(r'^##\s+(.+)$', note_text, re.MULTILINE)
        topics = [
            h.strip() for h in headings
            if len(h.strip()) > 2
            and not re.search(
                r'contents|table\s+of\s+contents|references|proficiency',
                h, re.IGNORECASE,
            )
        ]

    # ── 3. Last resort: single placeholder node ─────────────────────────
    if not topics:
        return {
            'nodes': [{'id': 1, 'label': 'Lecture Topics', 'full_label': 'Lecture Topics',
                        'status': 'partial', 'x': 50, 'y': 50, 'mutation_count': 0}],
            'edges': [],
        }

    # ── Build nodes with grid distribution ──────────────────────────────
    total = len(topics)
    nodes: list[dict] = []
    # Arrange in rows of 3 to avoid a flat line
    cols = 3
    for i, label in enumerate(topics):
        col = i % cols
        row = i // cols
        num_rows = (total + cols - 1) // cols
        x = round(15 + (col / max(cols - 1, 1)) * 70)   # 15–85%
        y = round(15 + (row / max(num_rows - 1, 1)) * 70) if num_rows > 1 else 50  # 15–85%
        nodes.append({
            'id': i + 1,
            'label': label[:30],
            'full_label': label,
            'status': 'partial',
            'x': x,
            'y': y,
            'mutation_count': 0,
        })

    edges: list[list[int]] = [[i, i + 1] for i in range(1, total)]
    return {'nodes': nodes, 'edges': edges}


# Keep the public name for any direct callers
extract_concepts = extract_topics_from_contents


async def llm_extract_concepts(note_text: str) -> dict:
    """
    Build a knowledge graph from generated notes.

    Primary: LLM-powered relationship detection (Azure OpenAI → Groq → fallback).
    Fallback: deterministic Contents/heading extraction.
    """
    try:
        from agents.graph_builder import build_knowledge_graph
        return await build_knowledge_graph(note_text)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "graph_builder failed — falling back to deterministic extraction", exc_info=True,
        )
        return extract_topics_from_contents(note_text)
