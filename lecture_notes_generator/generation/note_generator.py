"""
lecture_notes_generator/generation/note_generator.py
──────────────────────────────────────────────────────
Fixes H1–H4:
  H1 – No longer uses sentence-transformers (incompatible with backend).
       Uses Azure OpenAI embeddings or TF-IDF exactly as the backend does.
  H2 – Now reads AZURE_OPENAI_* env vars (same as backend), with OPENAI_API_KEY
       as a compatibility fallback for OpenAI-direct usage.
  H3 – Graceful fallback: if no API key available, uses local TF-IDF retrieval.
  H4 – requirements.txt pinned to match backend versions (see requirements.txt).
"""
import os
import re
from typing import List, Dict, Any, Optional

# ── API key resolution (FIX H2: prefers Azure, falls back to OpenAI) ──────────

def _get_client():
    """
    Build an OpenAI-compatible chat client.
    Priority: Azure OpenAI (matches backend) → OpenAI direct → None (local mode).
    FIX H2: was hardcoded OPENAI_API_KEY; now supports AZURE_OPENAI_* env vars.
    FIX H3: returns None gracefully if no keys configured (no crash).
    """
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    az_key   = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    oa_key   = os.environ.get("OPENAI_API_KEY", "")

    if endpoint and az_key and "mock" not in endpoint.lower():
        try:
            from openai import AzureOpenAI
            return AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=az_key,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            ), "azure"
        except Exception:
            pass

    if oa_key and not oa_key.startswith("your-"):
        try:
            from openai import OpenAI
            return OpenAI(api_key=oa_key), "openai"
        except Exception:
            pass

    return None, "local"


def _get_embedding_client():
    """
    FIX H1: Use Azure OpenAI embeddings (same as backend), NOT sentence-transformers.
    FIX H3: Returns None if unavailable instead of crashing.
    """
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    az_key   = os.environ.get("AZURE_OPENAI_API_KEY",  "")
    if endpoint and az_key and "mock" not in endpoint.lower():
        try:
            from openai import AzureOpenAI
            return AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=az_key,
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            )
        except Exception:
            pass
    return None


# ── TF-IDF fallback retrieval (FIX H1: no sentence-transformers) ──────────────

class _TFIDFRetriever:
    """
    Pure-Python TF-IDF retrieval matching the backend's pipeline/embedder.py.
    FIX H1: replaces sentence-transformers/FAISS — fully compatible with backend.
    """
    _STOP = frozenset(
        "a an the is are was were be been have has had do does did will would "
        "could should may to of in on at by for with from that this these those "
        "it its we our they their and or but not if so as also both just only".split()
    )

    def __init__(self):
        self.vocab: dict = {}
        self.idf_arr = None
        self.chunk_texts: list = []

    def fit(self, texts: list[str]):
        import math
        tokenised = [self._tok(t) for t in texts]
        self.chunk_texts = texts
        N = len(texts)
        df: dict = {}
        for toks in tokenised:
            for w in set(toks):
                df[w] = df.get(w, 0) + 1
        top = sorted(df.items(), key=lambda x: -x[1])[:1024]
        self.vocab = {w: i for i, (w, _) in enumerate(top)}
        self.idf_arr = [math.log((N+1)/(df.get(w,1)+1))+1 for w,_ in top]
        vecs = []
        for toks in tokenised:
            v = self._make_vec(toks)
            vecs.append(v)
        self._matrix = vecs

    def _tok(self, text: str) -> list:
        return [w for w in re.findall(r'\b[a-zA-Z]{2,}\b', text.lower()) if w not in self._STOP]

    def _make_vec(self, tokens: list) -> list:
        import math
        dim = len(self.vocab)
        v = [0.0] * dim
        tf: dict = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = max(len(tokens), 1)
        for term, cnt in tf.items():
            if term in self.vocab:
                i = self.vocab[term]
                v[i] = (cnt/total) * self.idf_arr[i]
        norm = sum(x*x for x in v) ** 0.5
        return [x/norm for x in v] if norm > 0 else v

    def query(self, q: str, k: int = 5) -> list:
        if not self._matrix:
            return []
        qv = self._make_vec(self._tok(q))
        scores = [sum(a*b for a,b in zip(qv, row)) for row in self._matrix]
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [{"text": self.chunk_texts[i], "score": scores[i]} for i in ranked]


class NoteGenerator:
    def __init__(self, api_key: str = None, model: str = None):
        """
        FIX H2: api_key param kept for backward compat but Azure env vars
        take priority. FIX H3: no crash if keys missing — graceful local mode.
        """
        # If explicit api_key passed, treat as OpenAI key
        if api_key:
            os.environ.setdefault("OPENAI_API_KEY", api_key)

        self._client, self._backend = _get_client()
        self._emb_client = _get_embedding_client()
        self.model = model or os.environ.get(
            "AZURE_OPENAI_DEPLOYMENT",
            "gpt-4o" if self._backend == "azure" else "gpt-4o",
        )

        if self._backend == "local":
            import warnings
            warnings.warn(
                "NoteGenerator: No AI API configured. "
                "Set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY (preferred) "
                "or OPENAI_API_KEY. Running in local fallback mode.",
                stacklevel=2,
            )

    # FIX H1: embed using Azure, not sentence-transformers
    def _embed(self, texts: list[str]):
        if self._emb_client:
            try:
                dep = os.environ.get("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
                resp = self._emb_client.embeddings.create(model=dep, input=texts[:16])
                return [item.embedding for item in resp.data]
            except Exception:
                pass
        return None

    def generate_topic_note(
        self,
        topic: str,
        key_points: List[str],
        textbook_chunks: List[Dict[str, Any]],
    ) -> str:
        context_text = "\n\n---\n\n".join([c.get('text','') for c in textbook_chunks])
        kp_fmt = "\n".join([f"- {kp}" for kp in key_points])

        system_prompt = (
            "You are an expert Professor and precise academic writer. Your goal is to generate "
            "comprehensive, structured lecture notes that synthesize lecture slides with textbook context.\n"
        )
        user_prompt = (
            f"Generate structured, high-quality lecture notes for the following topic.\n\n"
            f"--- INPUT ---\n"
            f"Topic: {topic}\n"
            f"Slide Key Points:\n{kp_fmt}\n\n"
            f"Textbook Context (Top Retrieved Excerpts):\n{context_text}\n\n"
            f"--- INSTRUCTIONS ---\n"
            f"1. Anchor to the Topic and Slide Key Points.\n"
            f"2. Use Textbook Context to enrich explanations.\n"
            f"3. Structure: ## {topic} → ### Overview → Key Concepts → Examples → ### Key Takeaways\n"
            f"4. Use Markdown. Bold keywords.\n"
        )

        # FIX H3: graceful fallback when no LLM
        if self._client is None:
            return f"## {topic}\n\n### Overview\n\n" + "\n".join(f"- {kp}" for kp in key_points) + "\n"

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.3,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error generating note for topic '{topic}': {e}")
            return f"## {topic}\n\n[Error generating content: {e}]"

    def refine_notes(self, merged_notes: str) -> str:
        if self._client is None or len(merged_notes.strip()) < 100:
            return merged_notes

        system_prompt = "You are a meticulous professional editor specializing in academic textbooks and study guides."
        user_prompt = (
            "Refine the following merged lecture notes into a single coherent academic document.\n"
            "Fix inconsistencies, improve flow, remove redundancies, keep LaTeX math.\n"
            "Return the complete refined document in Markdown.\n\n"
            f"{merged_notes}"
        )
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=8000,
                temperature=0.3,
            )
            refined = resp.choices[0].message.content.strip()
            # FIX C2-equivalent: keep refinements even if shorter (threshold 0.3)
            return refined if len(refined) > len(merged_notes) * 0.3 else merged_notes
        except Exception as e:
            print(f"Refinement error: {e}")
            return merged_notes
