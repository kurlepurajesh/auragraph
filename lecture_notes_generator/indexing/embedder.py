from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

class Embedder:
    def __init__(self, model_name: str = \"all-MiniLM-L6-v2\"):
        \"\"\"
        Initializes the sentence transformer model.
        Options:
        - all-MiniLM-L6-v2 (fast)
        - bge-large-en (high accuracy but slower)
        \"\"\"
        self.model = SentenceTransformer(model_name)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        \"\"\"
        Generates embeddings for a list of texts.
        Returns a numpy array of shape (num_texts, embedding_dim).
        \"\"\"
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings

    def embed_query(self, query: str) -> np.ndarray:
        \"\"\"
        Generates an embedding for a single query.
        Returns a numpy array of shape (1, embedding_dim).
        \"\"\"
        embedding = self.model.encode([query], convert_to_numpy=True, show_progress_bar=False)
        return embedding
