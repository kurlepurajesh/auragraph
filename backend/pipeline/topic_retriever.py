"""
pipeline/topic_retriever.py
────────────────────────────
Step 5 — Topic-Based Retrieval.

For each lecture topic, builds a rich retrieval query from:
  - topic name
  - key points from slides

Then searches the vector DB to find the 5-7 most relevant textbook chunks.

This ensures each note generation call gets exactly the textbook context
it needs — not a generic dump of the whole book.

Design principles:
  - Query construction is deterministic (no LLM)
  - Retrieval is semantic (vector similarity)
  - Results are deduplicated across topics (same chunk can serve multiple topics)
  - Fallback: if vector DB is empty, returns empty list (caller handles gracefully)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from pipeline.chunker import TextChunk
from pipeline.embedder import Embedder
from pipeline.slide_analyzer import SlideTopic
from pipeline.vector_db import VectorDB

logger = logging.getLogger(__name__)

# How many textbook chunks to retrieve per topic
TOP_K_PER_TOPIC = 10

# Max chars of textbook context to pass into note generation per topic
MAX_CONTEXT_CHARS = 14_000


def _build_retrieval_query(topic: SlideTopic) -> str:
    """
    Build a rich retrieval query string for a topic.

    Concatenates topic name + key points into a single string so the
    embedding captures both the concept name and its specific facets.
    """
    parts = [topic.topic]
    for kp in topic.key_points[:4]:
        if kp.strip():
            parts.append(kp.strip())
    return " ".join(parts)


def _format_chunks_as_context(chunks: list[tuple[TextChunk, float]]) -> str:
    """
    Format retrieved textbook chunks into a compact context string for the LLM.
    Budget-capped at MAX_CONTEXT_CHARS.
    Includes source metadata so the LLM knows where content came from.
    """
    parts = []
    used  = 0
    for chunk, score in chunks:
        meta = ""
        if chunk.chapter:
            meta = f"[Chapter: {chunk.chapter}"
            if chunk.section:
                meta += f" | Section: {chunk.section}"
            meta += "]"
        else:
            meta = "[Textbook]"

        block = f"{meta}\n{chunk.text}\n"
        if used + len(block) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - used - len(meta) - 10
            if remaining > 200:
                block = f"{meta}\n{chunk.text[:remaining].rsplit(' ', 1)[0]} …\n"
            else:
                break
        parts.append(block)
        used += len(block)

    return "\n---\n".join(parts) if parts else ""


class TopicRetriever:
    """
    Retrieves relevant textbook chunks for each lecture topic.

    Usage:
        retriever = TopicRetriever(vector_db, embedder)
        context = retriever.retrieve_for_topic(topic)
        # context is a formatted string ready to inject into the note prompt
    """

    def __init__(self, vector_db: VectorDB, embedder: Embedder):
        self._db      = vector_db
        self._embedder = embedder

    def retrieve_for_topic(
        self,
        topic: SlideTopic,
        top_k: int = TOP_K_PER_TOPIC,
    ) -> str:
        """
        Retrieve and format textbook context for a single topic.

        Returns a formatted string of relevant textbook passages,
        or empty string if nothing relevant is found.
        """
        if self._db.size == 0:
            return ""

        query     = _build_retrieval_query(topic)
        query_vec = self._embedder.embed_query(query)

        if query_vec is None:
            logger.warning("TopicRetriever: could not embed query for '%s'", topic.topic)
            return ""

        results = self._db.search(query_vec, top_k=top_k)

        if not results:
            return ""

        # Filter out low-similarity chunks; keep only reasonably relevant ones
        results = [(c, s) for c, s in results if s >= 0.03]

        if not results:
            logger.debug("TopicRetriever: no relevant chunks for '%s' (all below threshold)", topic.topic)
            return ""

        logger.debug(
            "TopicRetriever: '%s' → %d chunks (top score=%.3f)",
            topic.topic, len(results), results[0][1]
        )
        return _format_chunks_as_context(results)

    def retrieve_all_topics(
        self,
        topics: list[SlideTopic],
        top_k: int = TOP_K_PER_TOPIC,
    ) -> dict[str, str]:
        """
        Retrieve textbook context for all topics at once.

        Returns a dict mapping topic name → formatted context string.
        """
        return {
            topic.topic: self.retrieve_for_topic(topic, top_k=top_k)
            for topic in topics
        }
