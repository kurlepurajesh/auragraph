"""
Mock Cosmos DB for State Management Development
Tracks Mastery States of Concepts — per-user isolated storage.

FIX (round 4):
  • Per-user DB files (mock_db_<username>.json) prevent one user's mastery
    updates from clobbering another's.
  • threading.Lock on all read/write paths prevents concurrent-write corruption.
"""
import json
import os
import re
import threading
from pathlib import Path

_DB_DIR  = Path(__file__).parent.parent
_DB_LOCK = threading.Lock()

_DEFAULT_NODES = [
    {"id": 1, "label": "Fourier Transform",  "status": "mastered",   "x": 50, "y": 18, "mutation_count": 0},
    {"id": 2, "label": "Convolution Theorem","status": "struggling",  "x": 50, "y": 44, "mutation_count": 0},
    {"id": 3, "label": "LTI Systems",         "status": "partial",    "x": 20, "y": 70, "mutation_count": 0},
    {"id": 4, "label": "Freq. Response",      "status": "mastered",   "x": 80, "y": 70, "mutation_count": 0},
    {"id": 5, "label": "Z-Transform",         "status": "partial",    "x": 50, "y": 90, "mutation_count": 0},
]
_DEFAULT_EDGES = [[1, 2], [2, 3], [2, 4], [3, 5], [4, 5]]


def _db_path(username: str) -> Path:
    """Return per-user DB path, sanitising the username to a safe filename."""
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", username) if username else "anonymous"
    return _DB_DIR / f"mock_db_{safe}.json"


def get_db(username: str = "anonymous") -> dict:
    """Return the mastery graph for *username*, creating it if absent."""
    path = _db_path(username)
    with _DB_LOCK:
        if not path.exists():
            db: dict = {
                "nodes": [dict(n) for n in _DEFAULT_NODES],
                "edges": [list(e) for e in _DEFAULT_EDGES],
            }
            with open(path, "w", encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False)
            return db
        with open(path, "r", encoding='utf-8') as f:
            return json.load(f)


def save_db(db: dict, username: str = "anonymous") -> None:
    """Persist *db* for *username* atomically (write to tmp, then rename)."""
    path = _db_path(username)
    tmp  = path.with_suffix(".tmp")
    with _DB_LOCK:
        with open(tmp, "w", encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False)
        os.replace(tmp, path)


def increment_mutation_count(node_label: str, username: str = "anonymous") -> None:
    """Increment the mutation_count field of the matching node. Silent no-op if not found."""
    path = _db_path(username)
    with _DB_LOCK:
        if not path.exists():
            return
        with open(path, "r", encoding='utf-8') as f:
            db = json.load(f)
        matched = False
        for node in db["nodes"]:
            if node["label"].lower() == node_label.lower():
                node["mutation_count"] = node.get("mutation_count", 0) + 1
                matched = True
                break
        if not matched:
            return
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False)
        os.replace(tmp, path)


def update_node_status(node_label: str, new_status: str, username: str = "anonymous"):
    """Update a single node's status in the per-user graph. Returns the node or None."""
    path = _db_path(username)
    with _DB_LOCK:
        # Read
        if not path.exists():
            db: dict = {
                "nodes": [dict(n) for n in _DEFAULT_NODES],
                "edges": [list(e) for e in _DEFAULT_EDGES],
            }
        else:
            with open(path, "r") as f:
                db = json.load(f)
        # Mutate
        matched = None
        for node in db["nodes"]:
            if node["label"].lower() == node_label.lower():
                node["status"] = new_status
                matched = node
                break
        if matched is None:
            return None
        # Write
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(db, f)
        os.replace(tmp, path)
    return matched
