"""
pipeline/vector_db.py
─────────────────────
Pure-numpy cosine similarity vector store.

Functionally equivalent to FAISS IndexFlatIP for our use case (cosine search
over normalised vectors = inner product search), with no extra dependencies.

Features:
  - Add chunks with their embeddings
  - Search by query vector → top-k results with scores
  - Persist to / load from a notebook-specific JSON file
  - Handles both Azure (1536-dim) and TF-IDF (1024-dim) embeddings seamlessly

Design:
  Embeddings are stored as a numpy matrix (N × D).
  Search is a single matrix-vector multiply: scores = matrix @ query_vec
  This is O(N·D) — fast enough for tens of thousands of chunks.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from pipeline.chunker import TextChunk

logger = logging.getLogger(__name__)

STORE_DIR = Path(__file__).parent.parent / "knowledge_store"
STORE_DIR.mkdir(exist_ok=True)


class VectorDB:
    """
    In-memory cosine-similarity vector store for textbook chunks.

    All embeddings are assumed to be L2-normalised (unit vectors).
    Cosine similarity then equals dot product, computed via matrix multiply.
    """

    def __init__(self):
        self._chunks:     list[TextChunk] = []   # parallel list to _matrix rows
        self._matrix:     Optional[np.ndarray] = None  # shape (N, D)
        self._dim:        int = 0

    # ── Building the index ────────────────────────────────────────────────────

    def add_chunks(self, chunks: list[TextChunk]) -> None:
        """
        Add chunks (with embeddings already filled in) to the index.
        Replaces any existing data.
        """
        embedded = [c for c in chunks if c.embedding is not None]
        if not embedded:
            logger.warning("VectorDB.add_chunks: no chunks have embeddings")
            return

        self._chunks = embedded
        mat = np.array([c.embedding for c in embedded], dtype=np.float32)

        # Re-normalise in case embeddings came from disk without normalisation
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self._matrix = mat / norms
        self._dim    = self._matrix.shape[1]
        logger.info("VectorDB: indexed %d chunks (dim=%d)", len(self._chunks), self._dim)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 7,
        chapter_filter: Optional[str] = None,
    ) -> list[tuple[TextChunk, float]]:
        """
        Return top_k (chunk, score) pairs sorted by cosine similarity (desc).

        Args:
            query_vec:      1-D numpy array, same dim as stored embeddings.
            top_k:          Number of results to return.
            chapter_filter: If given, restrict to chunks from that chapter.
        """
        if self._matrix is None or len(self._chunks) == 0:
            return []

        # Normalise query vector
        qn = np.linalg.norm(query_vec)
        if qn == 0:
            return []
        q = query_vec.astype(np.float32) / qn

        # Handle dim mismatch (e.g. TF-IDF vocab size < stored dim)
        if q.shape[0] != self._dim:
            if q.shape[0] < self._dim:
                q = np.pad(q, (0, self._dim - q.shape[0]))
            else:
                q = q[:self._dim]

        # Cosine scores for all chunks
        scores = self._matrix @ q   # shape (N,)

        # Apply chapter filter
        mask = np.ones(len(self._chunks), dtype=bool)
        if chapter_filter:
            cf = chapter_filter.lower()
            for i, c in enumerate(self._chunks):
                if cf not in c.chapter.lower():
                    mask[i] = False
            if mask.sum() == 0:
                mask = np.ones(len(self._chunks), dtype=bool)  # fallback: no filter

        valid_indices = np.where(mask)[0]
        valid_scores  = scores[valid_indices]

        # Top-k from valid set
        if len(valid_indices) <= top_k:
            top_idx = valid_indices[np.argsort(-valid_scores)]
        else:
            top_local = np.argpartition(-valid_scores, top_k)[:top_k]
            top_local = top_local[np.argsort(-valid_scores[top_local])]
            top_idx   = valid_indices[top_local]

        return [(self._chunks[i], float(scores[i])) for i in top_idx]

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, nb_id: str) -> None:
        """Persist the vector index for a notebook to disk."""
        if not self._chunks:
            return
        path = STORE_DIR / f"{nb_id}_vectors.json"
        data = {
            "dim":    self._dim,
            "chunks": [c.to_dict() for c in self._chunks],
        }
        path.write_text(json.dumps(data, ensure_ascii=False))
        logger.info("VectorDB saved %d chunks to %s", len(self._chunks), path.name)

    def load(self, nb_id: str) -> bool:
        """
        Load a persisted vector index for a notebook.
        Returns True if successful, False if no index exists.
        """
        path = STORE_DIR / f"{nb_id}_vectors.json"
        if not path.exists():
            return False
        try:
            data   = json.loads(path.read_text())
            chunks = [TextChunk.from_dict(d) for d in data["chunks"]]
            self.add_chunks(chunks)
            logger.info("VectorDB loaded %d chunks from %s", len(self._chunks), path.name)
            return True
        except Exception as e:
            logger.warning("VectorDB load failed: %s", e)
            return False

    @staticmethod
    def delete(nb_id: str) -> None:
        """Delete persisted vector index for a notebook."""
        path = STORE_DIR / f"{nb_id}_vectors.json"
        if path.exists():
            path.unlink()

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def dim(self) -> int:
        return self._dim
