import re
from typing import List, Dict, Any

class Chunker:
    def __init__(self, chunk_size_words: int = 400, overlap_words: int = 50):
        \"\"\"
        A chunker using words as a proxy for tokens (1 word ~ 1.3 tokens usually).
        chunk_size_words: approximate size of chunks in words.
        \"\"\"
        self.chunk_size_words = chunk_size_words
        self.overlap_words = overlap_words

    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        \"\"\"
        Splits text into overlapping chunks, returning a list of dictionaries with metadata.
        \"\"\"
        words = re.split(r'\\s+', text.strip())
        chunks = []
        
        if not words:
            return chunks
            
        i = 0
        chunk_id = 0
        while i < len(words):
            end_index = min(i + self.chunk_size_words, len(words))
            chunk_words = words[i:end_index]
            chunk_text = \" \".join(chunk_words)
            
            chunks.append({
                \"chunk_id\": chunk_id,
                \"text\": chunk_text,
                \"chapter\": \"Unknown\", # Can be enhanced if structure is extracted
                \"section\": \"Unknown\", # Can be enhanced if structure is extracted
                # embedding will be added later
            })
            
            chunk_id += 1
            i += self.chunk_size_words - self.overlap_words
            
            # Prevent infinite loop on edge cases
            if self.chunk_size_words <= self.overlap_words:
                i += 1
                
        return chunks
