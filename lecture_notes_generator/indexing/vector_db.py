import faiss
import numpy as np
from typing import List, Dict, Any

class VectorDB:
    def __init__(self, embedding_dim: int):
        \"\"\"
        Initializes FAISS index for L2 distance (Inner Product is used for Cosine Similarity if normalized).
        We will use IndexFlatL2 for simplicity.
        \"\"\"
        self.dimension = embedding_dim
        self.index = faiss.IndexFlatL2(self.dimension)
        self.chunks: List[Dict[str, Any]] = []

    def add_chunks(self, chunks: List[Dict[str, Any]]):
        \"\"\"
        Adds chunk dictionaries to the store and their embeddings to the FAISS index.
        The chunks must already have an 'embedding' key with a numpy array.
        \"\"\"
        if not chunks:
            return
            
        embeddings = np.vstack([chunk['embedding'] for chunk in chunks]).astype('float32')
        self.index.add(embeddings)
        self.chunks.extend(chunks)

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        \"\"\"
        Searches the vector database for the top_k most similar chunks.
        query_embedding should be a 1D array or (1, dim) 2D array.
        \"\"\"
        if len(self.chunks) == 0:
            return []
            
        query_embedding = query_embedding.astype('float32')
        if len(query_embedding.shape) == 1:
            query_embedding = query_embedding.reshape(1, -1)
            
        distances, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for i in range(len(indices[0])):
            idx = indices[0][i]
            if idx != -1 and idx < len(self.chunks):
                results.append(self.chunks[idx])
                
        return results
