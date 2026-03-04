"""
Notebook Storage — AuraGraph
Persists notebooks (per user) in notebooks.json.
"""
import json, uuid
from datetime import datetime
from pathlib import Path

NOTEBOOKS_PATH = Path(__file__).parent.parent / "notebooks.json"


def _get_all():
    if not NOTEBOOKS_PATH.exists():
        NOTEBOOKS_PATH.write_text(json.dumps([]))
    return json.loads(NOTEBOOKS_PATH.read_text())


def _save_all(notebooks):
    NOTEBOOKS_PATH.write_text(json.dumps(notebooks, indent=2))


def create_notebook(user_id: str, name: str, course: str) -> dict:
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
    notebooks = _get_all()
    for nb in notebooks:
        if nb["id"] == nb_id:
            nb["graph"] = graph
            nb["updated_at"] = datetime.utcnow().isoformat()
            _save_all(notebooks)
            return nb
    return None


def delete_notebook(nb_id: str) -> bool:
    notebooks = _get_all()
    new = [nb for nb in notebooks if nb["id"] != nb_id]
    if len(new) == len(notebooks):
        return False
    _save_all(new)
    return True
