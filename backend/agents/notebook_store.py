"""
Notebook Storage — AuraGraph (SQLite v2)
Uses a shared auragraph.db with WAL mode.
Tables:
  notebooks  — one row per notebook (graph stored as JSON text)
  sections   — per-notebook topic/chapter sections for structured notes
"""
import json, logging, re, sqlite3, uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from agents.db_pool import pooled_conn

logger = logging.getLogger("auragraph")
DB_PATH = Path(__file__).parent.parent / "auragraph.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn():
    """Pooled connection context manager for the shared auragraph.db."""
    return pooled_conn(str(DB_PATH))


def _init_db():
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS notebooks (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                name        TEXT NOT NULL,
                course      TEXT NOT NULL DEFAULT '',
                note        TEXT NOT NULL DEFAULT '',
                proficiency TEXT NOT NULL DEFAULT 'Intermediate',
                graph       TEXT NOT NULL DEFAULT '{"nodes":[],"edges":[]}',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nb_user ON notebooks(user_id);

            CREATE TABLE IF NOT EXISTS sections (
                id          TEXT PRIMARY KEY,
                notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                title       TEXT NOT NULL,
                note_type   TEXT NOT NULL DEFAULT 'topic',
                content     TEXT NOT NULL DEFAULT '',
                order_idx   INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sec_nb ON sections(notebook_id, order_idx);
        """)
    _migrate_from_json()


def _migrate_from_json():
    json_path = Path(__file__).parent.parent / "notebooks.json"
    done_path = Path(__file__).parent.parent / "notebooks.json.migrated"
    if done_path.exists() or not json_path.exists():
        return
    try:
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        with _conn() as con:
            for nb in rows:
                graph = nb.get("graph", {"nodes": [], "edges": []})
                con.execute(
                    "INSERT OR IGNORE INTO notebooks VALUES (?,?,?,?,?,?,?,?,?)",
                    (nb["id"], nb["user_id"], nb["name"],
                     nb.get("course", ""), nb.get("note", ""),
                     nb.get("proficiency", "Intermediate"),
                     json.dumps(graph),
                     nb.get("created_at", _now()),
                     nb.get("updated_at", _now()))
                )
                if nb.get("note"):
                    _seed_sections_for_note(con, nb["id"], nb["note"])
        json_path.rename(done_path)
        logger.info("Migrated %d notebooks JSON -> SQLite", len(rows))
    except Exception as exc:
        logger.warning("notebooks.json migration failed: %s", exc)


def _seed_sections_for_note(con, nb_id: str, note: str):
    """Split ## headings in note text into section rows (idempotent)."""
    existing = con.execute(
        "SELECT COUNT(*) FROM sections WHERE notebook_id=?", (nb_id,)
    ).fetchone()[0]
    if existing:
        return
    parts = re.split(r"(?=^## )", note, flags=re.MULTILINE)
    parts = [p.strip() for p in parts if p.strip()]
    for idx, part in enumerate(parts):
        first_line = part.splitlines()[0].lstrip("#").strip()
        title = first_line[:120] if first_line else f"Section {idx + 1}"
        con.execute(
            "INSERT INTO sections VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), nb_id, title, "topic", part, idx, _now(), _now())
        )


def _nb_row(row) -> dict:
    if row is None:
        return None
    d = dict(row)
    try:
        d["graph"] = json.loads(d["graph"])
    except Exception:
        d["graph"] = {"nodes": [], "edges": []}
    return d


# ──────────────────────────────────────────────────────────────────────────────
# Notebook CRUD
# ──────────────────────────────────────────────────────────────────────────────

def create_notebook(user_id: str, name: str, course: str) -> dict:
    nb_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO notebooks VALUES (?,?,?,?,?,?,?,?,?)",
            (nb_id, user_id, name, course, "", "Intermediate",
             '{"nodes":[],"edges":[]}', now, now)
        )
    return {"id": nb_id, "user_id": user_id, "name": name, "course": course,
            "note": "", "proficiency": "Intermediate",
            "graph": {"nodes": [], "edges": []},
            "created_at": now, "updated_at": now}


def get_notebooks(user_id: str) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM notebooks WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,)
        ).fetchall()
    return [_nb_row(r) for r in rows]


def get_notebook(nb_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute("SELECT * FROM notebooks WHERE id=?", (nb_id,)).fetchone()
    return _nb_row(row)


def update_notebook_note(nb_id: str, note: str, proficiency: str = None) -> Optional[dict]:
    with _conn() as con:
        if proficiency:
            con.execute(
                "UPDATE notebooks SET note=?, proficiency=?, updated_at=? WHERE id=?",
                (note, proficiency, _now(), nb_id)
            )
        else:
            con.execute(
                "UPDATE notebooks SET note=?, updated_at=? WHERE id=?",
                (note, _now(), nb_id)
            )
        _seed_sections_for_note(con, nb_id, note)
        row = con.execute("SELECT * FROM notebooks WHERE id=?", (nb_id,)).fetchone()
    return _nb_row(row)


def update_notebook_graph(nb_id: str, graph: dict) -> Optional[dict]:
    with _conn() as con:
        con.execute(
            "UPDATE notebooks SET graph=?, updated_at=? WHERE id=?",
            (json.dumps(graph), _now(), nb_id)
        )
        row = con.execute("SELECT * FROM notebooks WHERE id=?", (nb_id,)).fetchone()
    return _nb_row(row)


def delete_notebook(nb_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM notebooks WHERE id=?", (nb_id,))
    return cur.rowcount > 0


# ──────────────────────────────────────────────────────────────────────────────
# Sections CRUD
# ──────────────────────────────────────────────────────────────────────────────

def get_sections(nb_id: str) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM sections WHERE notebook_id=? ORDER BY order_idx",
            (nb_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def create_section(nb_id: str, title: str, note_type: str = "topic") -> dict:
    with _conn() as con:
        max_idx = con.execute(
            "SELECT COALESCE(MAX(order_idx)+1,0) FROM sections WHERE notebook_id=?",
            (nb_id,)
        ).fetchone()[0]
        sec_id = str(uuid.uuid4())
        now = _now()
        con.execute(
            "INSERT INTO sections VALUES (?,?,?,?,?,?,?,?)",
            (sec_id, nb_id, title, note_type, "", max_idx, now, now)
        )
    return {"id": sec_id, "notebook_id": nb_id, "title": title,
            "note_type": note_type, "content": "", "order_idx": max_idx,
            "created_at": now, "updated_at": now}


def get_section(section_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute("SELECT * FROM sections WHERE id=?", (section_id,)).fetchone()
    return dict(row) if row else None


def update_section(section_id: str, **kwargs) -> Optional[dict]:
    allowed = {"title", "content", "note_type", "order_idx"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return get_section(section_id)
    fields["updated_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [section_id]
    with _conn() as con:
        con.execute(f"UPDATE sections SET {sets} WHERE id=?", vals)
        row = con.execute("SELECT * FROM sections WHERE id=?", (section_id,)).fetchone()
    return dict(row) if row else None


def delete_section(section_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM sections WHERE id=?", (section_id,))
    return cur.rowcount > 0


def reorder_sections(nb_id: str, order: list) -> list:
    """order = [{"id": ..., "order_idx": ...}, ...]"""
    with _conn() as con:
        for item in order:
            con.execute(
                "UPDATE sections SET order_idx=?, updated_at=? WHERE id=? AND notebook_id=?",
                (item["order_idx"], _now(), item["id"], nb_id)
            )
    return get_sections(nb_id)


def rebuild_note_from_sections(nb_id: str) -> str:
    """Reassemble the flat note text from ordered section content."""
    secs = get_sections(nb_id)
    return "\n\n".join(s["content"] for s in secs if s["content"].strip())


_init_db()
