"""
pipeline/embedder.py
────────────────────
Generates dense vector embeddings for textbook chunks.

Primary:  Azure OpenAI text-embedding-3-large  (1536-dim)
Fallback: TF-IDF sparse vectors normalised to unit length (pure numpy, no deps)

The fallback ensures the full pipeline works even without Azure credentials.
It is weaker than dense embeddings but still far better than keyword Jaccard
because it captures term frequency weighting across the whole corpus.
"""
from __future__ import annotations

import logging
import math
import os
import re
from typing import Optional

import numpy as np

from pipeline.chunker import TextChunk

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
EMBEDDING_DIM_AZURE = 1536   # text-embedding-3-large output dimension
EMBEDDING_DIM_TFIDF = 1024   # TF-IDF vocabulary cap (keeps memory reasonable)

_STOP = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "could should may might shall can cannot must to of in on at by for with "
    "from that this these those it its we our they their he she you your "
    "and or but not if so as also both just only even all any some such "
    "i into about over after before under between through during while "
    "because since although though because which when where how what who".split()
)


def _tokenise(text: str) -> list[str]:
    return [w for w in re.findall(r'\b[a-zA-Z]{2,}\b', text.lower()) if w not in _STOP]


# ── Azure OpenAI Embeddings ───────────────────────────────────────────────────

def _get_azure_embedding_client():
    """Build an openai.AzureOpenAI client for embeddings (lazy import)."""
    try:
        import openai
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        api_key  = os.environ.get("AZURE_OPENAI_API_KEY",  "")
        api_ver  = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")

        if not endpoint or not api_key or "mock" in endpoint.lower():
            return None

        return openai.AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_ver,
        )
    except Exception as e:
        logger.warning("openai client init failed: %s", e)
        return None


def _embed_azure(texts: list[str], client) -> Optional[np.ndarray]:
    """
    Call Azure text-embedding-3-large for a batch of texts.
    Returns shape (N, 1536) float32 array, or None on failure.
    """
    try:
        deployment = os.environ.get("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
        # Azure has a max batch size of 16 for embeddings
        all_vecs = []
        for i in range(0, len(texts), 16):
            batch = texts[i:i+16]
            resp  = client.embeddings.create(model=deployment, input=batch)
            vecs  = [item.embedding for item in resp.data]
            all_vecs.extend(vecs)
        arr = np.array(all_vecs, dtype=np.float32)
        # L2-normalise
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return arr / norms
    except Exception as e:
        logger.warning("Azure embedding call failed: %s", e)
        return None


# ── TF-IDF Fallback ───────────────────────────────────────────────────────────

class _TFIDFVectoriser:
    """
    Minimal TF-IDF vectoriser using numpy only.
    Vocabulary is built from the corpus and capped at EMBEDDING_DIM_TFIDF terms.
    """

    def __init__(self):
        self.vocab: dict[str, int] = {}   # term → column index
        self.idf:   np.ndarray     = np.array([])

    def fit(self, corpus: list[str]) -> None:
        """Build vocabulary and IDF weights from corpus."""
        # Count document frequency
        df: dict[str, int] = {}
        tokenised = [_tokenise(t) for t in corpus]
        N = len(corpus)
        for tokens in tokenised:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1

        # Pick top EMBEDDING_DIM_TFIDF terms by document frequency
        top_terms = sorted(df.items(), key=lambda x: -x[1])[:EMBEDDING_DIM_TFIDF]
        self.vocab = {term: idx for idx, (term, _) in enumerate(top_terms)}

        # IDF: log((N+1) / (df+1)) + 1  (smooth IDF)
        dim = len(self.vocab)
        idf_arr = np.ones(dim, dtype=np.float32)
        for term, idx in self.vocab.items():
            idf_arr[idx] = math.log((N + 1) / (df[term] + 1)) + 1.0
        self.idf = idf_arr

    def transform(self, texts: list[str]) -> np.ndarray:
        """Transform texts into L2-normalised TF-IDF vectors."""
        dim = len(self.vocab)
        if dim == 0:
            return np.zeros((len(texts), 1), dtype=np.float32)

        mat = np.zeros((len(texts), dim), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = _tokenise(text)
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            total = max(len(tokens), 1)
            for term, count in tf.items():
                if term in self.vocab:
                    col = self.vocab[term]
                    mat[row, col] = (count / total) * self.idf[col]

        # L2-normalise each row
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        return mat / norms


# ── Public API ────────────────────────────────────────────────────────────────

class Embedder:
    """
    Embed a list of TextChunks in-place.
    Tries Azure first; falls back to TF-IDF if Azure is unavailable.

    Usage:
        embedder = Embedder()
        embedder.embed_chunks(chunks)          # fills chunk.embedding
        vec = embedder.embed_query("Fourier")  # single query vector
    """

    def __init__(self):
        self._azure_client = _get_azure_embedding_client()
        self._tfidf: Optional[_TFIDFVectoriser] = None
        self._dim: int = 0

    def embed_chunks(self, chunks: list[TextChunk]) -> str:
        """
        Embed all chunks in-place (sets chunk.embedding).
        Returns 'azure' or 'tfidf' to indicate which backend was used.
        """
        if not chunks:
            return "none"

        texts = [c.text for c in chunks]

        # Try Azure
        if self._azure_client is not None:
            vecs = _embed_azure(texts, self._azure_client)
            if vecs is not None:
                self._dim = vecs.shape[1]
                for chunk, vec in zip(chunks, vecs):
                    chunk.embedding = vec.tolist()
                logger.info("Embedded %d chunks via Azure (dim=%d)", len(chunks), self._dim)
                return "azure"

        # Fallback: TF-IDF
        logger.info("Azure embedding unavailable — using TF-IDF fallback")
        vectoriser = _TFIDFVectoriser()
        vectoriser.fit(texts)
        vecs = vectoriser.transform(texts)
        self._tfidf = vectoriser
        self._dim   = vecs.shape[1]
        for chunk, vec in zip(chunks, vecs):
            chunk.embedding = vec.tolist()
        logger.info("Embedded %d chunks via TF-IDF (dim=%d)", len(chunks), self._dim)
        return "tfidf"

    def embed_query(self, query: str) -> Optional[np.ndarray]:
        """
        Embed a single query string.
        Returns a 1-D numpy array, or None if embeddings were never initialised.
        """
        if self._azure_client is not None:
            vecs = _embed_azure([query], self._azure_client)
            if vecs is not None:
                return vecs[0]

        if self._tfidf is not None:
            return self._tfidf.transform([query])[0]

        return None

    @property
    def dim(self) -> int:
        return self._dim
