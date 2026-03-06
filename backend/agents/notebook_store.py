"""
Notebook Storage — AuraGraph
Persists notebooks (per user) in notebooks.json.
"""
import json, uuid, threading
from datetime import datetime
from pathlib import Path

NOTEBOOKS_PATH = Path(__file__).parent.parent / "notebooks.json"

# Serialises all read-modify-write operations on notebooks.json
_NB_LOCK = threading.Lock()


def _get_all():
    if not NOTEBOOKS_PATH.exists():
        NOTEBOOKS_PATH.write_text(json.dumps([]), encoding='utf-8')
    return json.loads(NOTEBOOKS_PATH.read_text(encoding='utf-8'))


def _save_all(notebooks):
    # Caller must hold _NB_LOCK before calling this.
    NOTEBOOKS_PATH.write_text(json.dumps(notebooks, indent=2, ensure_ascii=False), encoding='utf-8')


def create_notebook(user_id: str, name: str, course: str) -> dict:
    with _NB_LOCK:
        notebooks = _get_all()
        nb = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "course": course,
            "note": "",
            "proficiency": "Intermediate",
            "graph": {"nodes": [], "edges": []},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        notebooks.append(nb)
        _save_all(notebooks)
    return nb


def get_notebooks(user_id: str) -> list:
    return [nb for nb in _get_all() if nb["user_id"] == user_id]


def get_notebook(nb_id: str) -> dict:
    return next((nb for nb in _get_all() if nb["id"] == nb_id), None)


def update_notebook_note(nb_id: str, note: str, proficiency: str = None) -> dict:
    with _NB_LOCK:
        notebooks = _get_all()
        for nb in notebooks:
            if nb["id"] == nb_id:
                nb["note"] = note
                if proficiency:
                    nb["proficiency"] = proficiency
                nb["updated_at"] = datetime.utcnow().isoformat()
                _save_all(notebooks)
                return nb
    return None


def update_notebook_graph(nb_id: str, graph: dict) -> dict:
    with _NB_LOCK:
        notebooks = _get_all()
        for nb in notebooks:
            if nb["id"] == nb_id:
                nb["graph"] = graph
                nb["updated_at"] = datetime.utcnow().isoformat()
                _save_all(notebooks)
                return nb
    return None


def delete_notebook(nb_id: str) -> bool:
    with _NB_LOCK:
        notebooks = _get_all()
        new = [nb for nb in notebooks if nb["id"] != nb_id]
        if len(new) == len(notebooks):
            return False
        _save_all(new)
    return True
