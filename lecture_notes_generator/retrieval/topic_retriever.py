from typing import List, Dict, Any

class TopicRetriever:
    def __init__(self, embedder, vector_db):
        \"\"\"
        Initializes retriever with the chosen embedder and populated vector DB.
        \"\"\"
        self.embedder = embedder
        self.vector_db = vector_db

    def retrieve_for_topic(self, topic_data: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
        \"\"\"
        Creates a query from the topic name and its key points,
        embeds the query, and searches the vector DB.
        
        topic_data format:
        {
            \"topic\": \"Topic Name\",
            \"key_points\": [\"point 1\", \"point 2\"]
        }
        \"\"\"
        topic_name = topic_data.get(\"topic\", \"\")
        key_points = topic_data.get(\"key_points\", [])
        
        # Formulate query
        query_parts = [topic_name] + key_points
        query_text = \" \".join(query_parts)
        
        # Get query embedding
        query_embedding = self.embedder.embed_query(query_text)
        
        # Search vector DB
        results = self.vector_db.search(query_embedding, top_k=top_k)
        
        return results
