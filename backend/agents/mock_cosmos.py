"""
Mock Cosmos DB for State Management Development
Tracks Mastery States of Concepts
"""
import json
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "mock_db.json"

def get_db():
    if not os.path.exists(DB_PATH):
        # Default starting state
        db = {
            "nodes": [
                { "id": 1, "label": "Fourier Transform", "status": "mastered", "x": 50, "y": 18 },
                { "id": 2, "label": "Convolution Theorem", "status": "struggling", "x": 50, "y": 44 },
                { "id": 3, "label": "LTI Systems", "status": "partial", "x": 20, "y": 70 },
                { "id": 4, "label": "Freq. Response", "status": "mastered", "x": 80, "y": 70 },
                { "id": 5, "label": "Z-Transform", "status": "partial", "x": 50, "y": 90 }
            ],
            "edges": [[1,2], [2,3], [2,4], [3,5], [4,5]]
        }
        with open(DB_PATH, "w") as f:
            json.dump(db, f)
        return db
    
    with open(DB_PATH, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_PATH, "w") as f:
        json.dump(db, f)

def update_node_status(node_label, new_status):
    db = get_db()
    for node in db["nodes"]:
        if node["label"].lower() == node_label.lower():
            node["status"] = new_status
            save_db(db)
            return node
    return None
