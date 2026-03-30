"""
Notebook Storage — AuraGraph (SQLite v2)
Uses a shared auragraph.db with WAL mode.
Tables:
  notebooks  — one row per notebook (graph stored as JSON text)
  sections   — per-notebook topic/chapter sections for structured notes
"""
import hashlib, json, logging, re, sqlite3, uuid, zlib
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from agents.db_pool import pooled_conn

logger = logging.getLogger("auragraph")
DB_PATH = Path(__file__).parent.parent / "auragraph.db"
MAX_NOTE_VERSIONS = 5


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

            CREATE TABLE IF NOT EXISTS doubts (
                id          TEXT PRIMARY KEY,
                notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                page_idx    INTEGER NOT NULL DEFAULT 0,
                doubt       TEXT NOT NULL,
                insight     TEXT NOT NULL DEFAULT '',
                gap         TEXT NOT NULL DEFAULT '',
                source      TEXT NOT NULL DEFAULT 'local',
                success     INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_doubts_nb ON doubts(notebook_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS annotations (
                id          TEXT PRIMARY KEY,
                notebook_id TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                page_idx    INTEGER NOT NULL DEFAULT 0,
                type        TEXT NOT NULL,
                data        TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ann_nb ON annotations(notebook_id, page_idx);

            CREATE TABLE IF NOT EXISTS quiz_runs (
                id              TEXT PRIMARY KEY,
                notebook_id     TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                quiz_type       TEXT NOT NULL DEFAULT 'general',
                status          TEXT NOT NULL DEFAULT 'completed',
                score           INTEGER NOT NULL DEFAULT 0,
                correct_answers INTEGER NOT NULL DEFAULT 0,
                total_questions INTEGER NOT NULL DEFAULT 0,
                questions       TEXT NOT NULL DEFAULT '[]',
                concepts_tested TEXT NOT NULL DEFAULT '[]',
                responses       TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL,
                completed_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_quiz_runs_nb_created
                ON quiz_runs(notebook_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS short_notes (
                notebook_id  TEXT PRIMARY KEY REFERENCES notebooks(id) ON DELETE CASCADE,
                content      TEXT NOT NULL DEFAULT '',
                source       TEXT NOT NULL DEFAULT 'local',
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS short_note_versions (
                notebook_id  TEXT PRIMARY KEY REFERENCES notebooks(id) ON DELETE CASCADE,
                content      TEXT NOT NULL DEFAULT '',
                source       TEXT NOT NULL DEFAULT 'local',
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS note_versions (
                id            TEXT PRIMARY KEY,
                notebook_id   TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                content_z     BLOB NOT NULL,
                content_hash  TEXT NOT NULL,
                content_len   INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_note_versions_nb_created
                ON note_versions(notebook_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS annotation_versions (
                id            TEXT PRIMARY KEY,
                notebook_id   TEXT NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                payload_z     BLOB NOT NULL,
                payload_hash  TEXT NOT NULL,
                item_count    INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ann_versions_nb_created
                ON annotation_versions(notebook_id, created_at DESC);
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


def _save_note_version(con, nb_id: str, previous_note: str) -> None:
    """Persist one compressed snapshot and keep only the last MAX_NOTE_VERSIONS."""
    note_text = (previous_note or "").strip()
    if not note_text:
        return

    note_hash = hashlib.sha256(note_text.encode("utf-8")).hexdigest()
    exists = con.execute(
        """
        SELECT 1 FROM note_versions
        WHERE notebook_id=? AND content_hash=?
        LIMIT 1
        """,
        (nb_id, note_hash),
    ).fetchone()
    if exists:
        return

    latest = con.execute(
        """
        SELECT content_hash FROM note_versions
        WHERE notebook_id=?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (nb_id,),
    ).fetchone()
    if latest and latest["content_hash"] == note_hash:
        return

    compressed = sqlite3.Binary(zlib.compress(note_text.encode("utf-8"), level=6))
    con.execute(
        """
        INSERT INTO note_versions (id, notebook_id, content_z, content_hash, content_len, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), nb_id, compressed, note_hash, len(note_text), _now()),
    )

    con.execute(
        """
        DELETE FROM note_versions
        WHERE notebook_id=?
          AND rowid NOT IN (
              SELECT rowid FROM note_versions
              WHERE notebook_id=?
              ORDER BY created_at DESC, rowid DESC
              LIMIT ?
          )
        """,
        (nb_id, nb_id, MAX_NOTE_VERSIONS),
    )


def _discard_latest_matching_note_version(con, nb_id: str, note_text: str) -> None:
    """Drop the newest snapshot when it matches note_text (used by undo restores)."""
    text = (note_text or "").strip()
    if not text:
        return
    note_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    latest = con.execute(
        """
        SELECT id, content_hash FROM note_versions
        WHERE notebook_id=?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (nb_id,),
    ).fetchone()
    if latest and latest["content_hash"] == note_hash:
        con.execute(
            "DELETE FROM note_versions WHERE id=? AND notebook_id=?",
            (latest["id"], nb_id),
        )


def _get_annotations_state(con, nb_id: str) -> tuple[str, str, int]:
    """Return canonical annotation state as (json_text, hash, item_count)."""
    rows = con.execute(
        """
        SELECT id, page_idx, type, data, created_at, updated_at
        FROM annotations
        WHERE notebook_id=?
        ORDER BY created_at ASC, id ASC
        """,
        (nb_id,),
    ).fetchall()
    items = [
        {
            "id": r["id"],
            "page_idx": int(r["page_idx"]),
            "type": r["type"],
            "data": json.loads(r["data"] or "{}"),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    payload = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return payload, payload_hash, len(items)


def _save_annotation_version(con, nb_id: str) -> None:
    """Snapshot annotation state with dedupe and capped retention."""
    payload, payload_hash, item_count = _get_annotations_state(con, nb_id)
    exists = con.execute(
        """
        SELECT 1 FROM annotation_versions
        WHERE notebook_id=? AND payload_hash=?
        LIMIT 1
        """,
        (nb_id, payload_hash),
    ).fetchone()
    if exists:
        return

    compressed = sqlite3.Binary(zlib.compress(payload.encode("utf-8"), level=6))
    con.execute(
        """
        INSERT INTO annotation_versions (id, notebook_id, payload_z, payload_hash, item_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), nb_id, compressed, payload_hash, item_count, _now()),
    )
    con.execute(
        """
        DELETE FROM annotation_versions
        WHERE notebook_id=?
          AND rowid NOT IN (
              SELECT rowid FROM annotation_versions
              WHERE notebook_id=?
              ORDER BY created_at DESC, rowid DESC
              LIMIT ?
          )
        """,
        (nb_id, nb_id, MAX_NOTE_VERSIONS),
    )


def update_notebook_note(
    nb_id: str,
    note: str,
    proficiency: str = None,
    save_version: bool = True,
    discard_matching_version: bool = False,
) -> Optional[dict]:
    def _split_note_pages_for_store(raw_note: str) -> list[str]:
        text = (raw_note or "").strip()
        if not text:
            return []
        pages = [p.strip() for p in re.split(r'(?m)^(?=## )', text) if p.strip()]
        if pages:
            return pages
        return [text]

    with _conn() as con:
        prev = con.execute("SELECT note FROM notebooks WHERE id=?", (nb_id,)).fetchone()
        prev_note = (prev["note"] if prev else "")
        if save_version and prev_note != (note or ""):
            _save_note_version(con, nb_id, prev_note)
        elif discard_matching_version:
            _discard_latest_matching_note_version(con, nb_id, note)

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

    # Keep mutation/read paths in sync with the latest saved note so undo does not reintroduce stale text.
    try:
        from agents.knowledge_store import store_note_pages
        store_note_pages(nb_id, _split_note_pages_for_store(note))
    except Exception as exc:
        logger.warning("note_pages sync failed for %s: %s", nb_id, exc)

    return _nb_row(row)


def update_notebook_graph(nb_id: str, graph: dict) -> Optional[dict]:
    with _conn() as con:
        con.execute(
            "UPDATE notebooks SET graph=?, updated_at=? WHERE id=?",
            (json.dumps(graph), _now(), nb_id)
        )
        row = con.execute("SELECT * FROM notebooks WHERE id=?", (nb_id,)).fetchone()
    return _nb_row(row)


def list_note_versions(nb_id: str, limit: int = MAX_NOTE_VERSIONS) -> list[dict]:
    """Return newest note snapshots for a notebook with compact metadata."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT id, content_z, content_len, created_at
            FROM note_versions
            WHERE notebook_id=?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (nb_id, max(1, int(limit or MAX_NOTE_VERSIONS))),
        ).fetchall()

    out = []
    for r in rows:
        preview = ""
        try:
            text = zlib.decompress(r["content_z"]).decode("utf-8", errors="replace")
            preview = " ".join(text.split())[:140]
        except Exception:
            preview = ""
        out.append(
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "content_len": int(r["content_len"] or 0),
                "preview": preview,
            }
        )
    return out


def restore_note_version(nb_id: str, version_id: str, proficiency: str = None) -> Optional[dict]:
    """Restore one stored note snapshot as current note without creating a new snapshot."""
    with _conn() as con:
        row = con.execute(
            "SELECT content_z FROM note_versions WHERE id=? AND notebook_id=?",
            (version_id, nb_id),
        ).fetchone()
    if not row:
        return None

    try:
        restored_note = zlib.decompress(row["content_z"]).decode("utf-8", errors="replace")
    except Exception:
        return None
    return update_notebook_note(nb_id, restored_note, proficiency=proficiency, save_version=False)


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

# ── Doubts API ─────────────────────────────────────────────────────────────────

def save_doubt(nb_id: str, doubt_entry: dict) -> bool:
    """Persist a single doubt entry to the backend DB.
    Replaces any existing entry with the same id (upsert)."""
    import time as _time
    try:
        with _conn() as con:
            con.execute(
                """
                INSERT INTO doubts (id, notebook_id, page_idx, doubt, insight, gap,
                                    source, success, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    notebook_id = excluded.notebook_id,
                    page_idx = excluded.page_idx,
                    doubt   = excluded.doubt,
                    insight = excluded.insight,
                    gap     = excluded.gap,
                    source  = excluded.source,
                    success = excluded.success,
                    created_at = excluded.created_at
                """,
                (
                    str(doubt_entry.get("id", "")),
                    nb_id,
                    int(doubt_entry.get("pageIdx", 0)),
                    str(doubt_entry.get("doubt", "")),
                    str(doubt_entry.get("insight", "")),
                    str(doubt_entry.get("gap", "")),
                    str(doubt_entry.get("source", "local")),
                    1 if doubt_entry.get("success") else 0,
                    str(doubt_entry.get("time", "")),
                ),
            )
        return True
    except Exception as exc:
        import logging as _log
        _log.getLogger("auragraph").warning("save_doubt failed: %s", exc)
        return False


def get_doubts(nb_id: str) -> list:
    """Return all doubts for a notebook, newest first."""
    try:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM doubts WHERE notebook_id=? ORDER BY created_at DESC",
                (nb_id,),
            ).fetchall()
        return [
            {
                "id":       r["id"],
                "pageIdx":  r["page_idx"],
                "doubt":    r["doubt"],
                "insight":  r["insight"],
                "gap":      r["gap"],
                "source":   r["source"],
                "success":  bool(r["success"]),
                "time":     r["created_at"],
            }
            for r in rows
        ]
    except Exception as exc:
        import logging as _log
        _log.getLogger("auragraph").warning("get_doubts failed: %s", exc)
        return []


def delete_doubt(nb_id: str, doubt_id: str) -> bool:
    """Delete a single doubt entry."""
    try:
        with _conn() as con:
            con.execute(
                "DELETE FROM doubts WHERE id=? AND notebook_id=?",
                (doubt_id, nb_id),
            )
        return True
    except Exception:
        return False



# ── Annotations API ────────────────────────────────────────────────────────────

def get_annotations(nb_id: str) -> list:
    """Return all annotations for a notebook."""
    try:
        with _conn() as con:
            rows = con.execute(
                "SELECT * FROM annotations WHERE notebook_id=? ORDER BY created_at ASC",
                (nb_id,),
            ).fetchall()
        return [
            {
                "id":          r["id"],
                "notebook_id": r["notebook_id"],
                "page_idx":    r["page_idx"],
                "type":        r["type"],
                "data":        json.loads(r["data"]),
                "created_at":  r["created_at"],
                "updated_at":  r["updated_at"],
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("get_annotations failed: %s", exc)
        return []


def save_annotation(nb_id: str, ann: dict) -> bool:
    """Upsert a single annotation (highlight, sticky, or drawing)."""
    try:
        now = _now()
        with _conn() as con:
            ann_id = str(ann.get("id", ""))
            new_data = json.dumps(ann.get("data", {}))
            existing = con.execute(
                "SELECT page_idx, type, data FROM annotations WHERE id=? AND notebook_id=?",
                (ann_id, nb_id),
            ).fetchone()
            changed = (
                existing is None or
                int(existing["page_idx"]) != int(ann.get("page_idx", 0)) or
                str(existing["type"] or "") != str(ann.get("type", "highlight")) or
                str(existing["data"] or "{}") != new_data
            )
            if changed:
                _save_annotation_version(con, nb_id)

            con.execute(
                """
                INSERT INTO annotations (id, notebook_id, page_idx, type, data, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    data       = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (
                    ann_id,
                    nb_id,
                    int(ann.get("page_idx", 0)),
                    str(ann.get("type", "highlight")),
                    new_data,
                    str(ann.get("created_at", now)),
                    now,
                ),
            )
        return True
    except Exception as exc:
        logger.warning("save_annotation failed: %s", exc)
        return False


def delete_annotation(nb_id: str, ann_id: str) -> bool:
    """Delete a single annotation."""
    try:
        with _conn() as con:
            existing = con.execute(
                "SELECT 1 FROM annotations WHERE id=? AND notebook_id=?",
                (ann_id, nb_id),
            ).fetchone()
            if existing:
                _save_annotation_version(con, nb_id)
            con.execute(
                "DELETE FROM annotations WHERE id=? AND notebook_id=?",
                (ann_id, nb_id),
            )
        return True
    except Exception:
        return False


def delete_all_annotations(nb_id: str) -> bool:
    """Delete all annotations for a notebook (e.g. on clear-all)."""
    try:
        with _conn() as con:
            has_any = con.execute(
                "SELECT 1 FROM annotations WHERE notebook_id=? LIMIT 1",
                (nb_id,),
            ).fetchone()
            if has_any:
                _save_annotation_version(con, nb_id)
            con.execute("DELETE FROM annotations WHERE notebook_id=?", (nb_id,))
        return True
    except Exception:
        return False


# ── Quiz Runs API ─────────────────────────────────────────────────────────────

def create_quiz_run(nb_id: str, payload: dict) -> str:
    """Create a quiz run row and return run id (used by complete endpoint)."""
    run_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO quiz_runs
            (id, notebook_id, quiz_type, status, score, correct_answers,
             total_questions, questions, concepts_tested, responses, created_at, completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                nb_id,
                str(payload.get("quiz_type", "general")),
                str(payload.get("status", "completed")),
                int(payload.get("score", 0) or 0),
                int(payload.get("correct_answers", payload.get("score", 0)) or 0),
                int(payload.get("total_questions", 0) or 0),
                json.dumps(payload.get("questions", [])),
                json.dumps(payload.get("concepts_tested", [])),
                json.dumps(payload.get("responses", [])),
                str(payload.get("created_at", now)),
                str(payload.get("completed_at", now)),
            ),
        )
    return run_id


def complete_quiz_run(nb_id: str, payload: dict) -> str:
    """Persist a completed quiz attempt in one call."""
    payload = dict(payload or {})
    payload.setdefault("status", "completed")
    payload.setdefault("correct_answers", payload.get("score", 0))
    payload.setdefault("total_questions", len(payload.get("questions", []) or []))
    return create_quiz_run(nb_id, payload)


def list_quiz_runs(nb_id: str, limit: int = 100) -> list:
    """Return quiz history newest first for a notebook."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM quiz_runs
            WHERE notebook_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (nb_id, max(1, int(limit or 100))),
        ).fetchall()

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "notebook_id": r["notebook_id"],
            "quiz_type": r["quiz_type"],
            "status": r["status"],
            "score": r["score"],
            "correct_answers": r["correct_answers"],
            "total_questions": r["total_questions"],
            "questions": json.loads(r["questions"] or "[]"),
            "concepts_tested": json.loads(r["concepts_tested"] or "[]"),
            "responses": json.loads(r["responses"] or "[]"),
            "created_at": r["created_at"],
            "completed_at": r["completed_at"],
        })
    return out


# ── Short Notes API ───────────────────────────────────────────────────────────

def get_short_note(nb_id: str) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT notebook_id, content, source, updated_at FROM short_notes WHERE notebook_id=?",
            (nb_id,),
        ).fetchone()
        prev = con.execute(
            "SELECT 1 FROM short_note_versions WHERE notebook_id=?",
            (nb_id,),
        ).fetchone()
    if not row:
        return {"content": "", "source": "", "updated_at": "", "has_previous": bool(prev)}
    return {
        "content": row["content"] or "",
        "source": row["source"] or "",
        "updated_at": row["updated_at"] or "",
        "has_previous": bool(prev),
    }


def save_short_note(nb_id: str, content: str, source: str = "local") -> dict:
    now = _now()
    clean_content = (content or "").strip()
    clean_source = (source or "local").strip() or "local"

    with _conn() as con:
        current = con.execute(
            "SELECT content, source, updated_at FROM short_notes WHERE notebook_id=?",
            (nb_id,),
        ).fetchone()

        # Keep exactly one previous snapshot for non-destructive undo preview.
        if current and (current["content"] or "").strip() and (current["content"] or "").strip() != clean_content:
            con.execute(
                """
                INSERT INTO short_note_versions (notebook_id, content, source, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(notebook_id) DO UPDATE SET
                    content=excluded.content,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (nb_id, current["content"], current["source"], current["updated_at"] or now),
            )

        con.execute(
            """
            INSERT INTO short_notes (notebook_id, content, source, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(notebook_id) DO UPDATE SET
                content=excluded.content,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (nb_id, clean_content, clean_source, now),
        )

        prev = con.execute(
            "SELECT 1 FROM short_note_versions WHERE notebook_id=?",
            (nb_id,),
        ).fetchone()

    return {
        "content": clean_content,
        "source": clean_source,
        "updated_at": now,
        "has_previous": bool(prev),
    }


def get_short_note_previous(nb_id: str) -> dict:
    with _conn() as con:
        row = con.execute(
            "SELECT content, source, updated_at FROM short_note_versions WHERE notebook_id=?",
            (nb_id,),
        ).fetchone()
    if not row:
        return {"content": "", "source": "", "updated_at": "", "has_previous": False}
    return {
        "content": row["content"] or "",
        "source": row["source"] or "",
        "updated_at": row["updated_at"] or "",
        "has_previous": True,
    }


# ── Feedback API ───────────────────────────────────────────────────────────────

def _ensure_feedback_table():
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS feedback (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL DEFAULT '',
                user_email  TEXT NOT NULL DEFAULT '',
                context     TEXT NOT NULL DEFAULT 'dashboard',
                notebook_id TEXT,
                rating      INTEGER,
                liked       TEXT NOT NULL DEFAULT '',
                disliked    TEXT NOT NULL DEFAULT '',
                category    TEXT NOT NULL DEFAULT 'general',
                message     TEXT NOT NULL DEFAULT '',
                page_url    TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fb_user ON feedback(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_fb_ctx  ON feedback(context, created_at DESC);
        """)

_ensure_feedback_table()


def save_feedback(entry: dict) -> str:
    fid = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """INSERT INTO feedback
               (id,user_id,user_email,context,notebook_id,rating,liked,
                disliked,category,message,page_url,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fid,
                str(entry.get("user_id", "")),
                str(entry.get("user_email", "")),
                str(entry.get("context", "dashboard")),
                entry.get("notebook_id"),
                entry.get("rating"),
                str(entry.get("liked", "")),
                str(entry.get("disliked", "")),
                str(entry.get("category", "general")),
                str(entry.get("message", "")),
                str(entry.get("page_url", "")),
                now,
            ),
        )
    return fid


def get_all_feedback(limit: int = 200) -> list:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


_FB_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "is", "are",
    "was", "were", "be", "this", "that", "it", "its", "as", "at", "by", "from", "my",
    "we", "our", "your", "you", "very", "more", "less", "too", "not", "but", "if", "so",
    "can", "could", "should", "would", "please", "app", "auragraph", "notes", "note", "quiz",
    "questions", "question", "mutation", "general",
}


def _normalise_feedback_category(raw: str) -> str:
    c = (raw or "").strip().lower()
    if c in {"notes", "note", "notes quality", "note quality"}:
        return "notes"
    if c in {"questions", "question", "quiz", "quiz questions", "quizzes"}:
        return "questions"
    if c in {"mutation", "note mutation", "note mutation/doubts", "rewrite", "rewrite page"}:
        return "mutation"
    if c in {"doubts", "doubt", "doubt answers", "ask doubt"}:
        return "doubts"
    return c or "general"


def _is_feedback_injection_like(text: str) -> bool:
    t = (text or "").lower()
    bad = (
        "ignore previous",
        "ignore all instructions",
        "system prompt",
        "developer message",
        "act as",
        "jailbreak",
        "do anything now",
        "reveal prompt",
    )
    return any(k in t for k in bad)


def _clean_feedback_line(text: str) -> str:
    line = re.sub(r"\s+", " ", (text or "").strip())
    line = re.sub(r"^[\-\*\d\)\.(\s]+", "", line)
    line = line.replace("\u2019", "'")
    line = line.strip(" \t\r\n\"'")
    if len(line) > 180:
        line = line[:180].rsplit(" ", 1)[0].strip()
    return line


def _feedback_line_tokens(line: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", (line or "").lower())
    return [t for t in toks if len(t) >= 3 and t not in _FB_STOPWORDS]


def get_feedback_prompt_guidance(tag: str, limit: int = 400, max_points: int = 4) -> str:
    """
    Build a short, sanitised guidance block from recent feedback for one tag.
    Output: 3-4 bullet points (when enough signals exist), suitable for prompt injection.
    """
    target = _normalise_feedback_category(tag)
    if target not in {"notes", "mutation", "questions", "doubts"}:
        return ""

    rows = get_all_feedback(limit=max(50, int(limit or 400)))
    lines: list[str] = []

    for row in rows:
        if _normalise_feedback_category(str(row.get("category", ""))) != target:
            continue
        parts = [
            str(row.get("disliked", "")),
            str(row.get("message", "")),
            str(row.get("liked", "")),
        ]
        for part in parts:
            if not part.strip() or _is_feedback_injection_like(part):
                continue
            chunks = re.split(r"[\n\r\.!?;]+", part)
            for ch in chunks:
                cleaned = _clean_feedback_line(ch)
                if len(cleaned) < 12:
                    continue
                if _is_feedback_injection_like(cleaned):
                    continue
                lines.append(cleaned)

    if not lines:
        return ""

    freq = Counter()
    for ln in lines:
        freq.update(_feedback_line_tokens(ln))

    seen_norm: set[str] = set()
    ranked: list[tuple[float, str]] = []
    for ln in lines:
        norm = re.sub(r"\W+", " ", ln.lower()).strip()
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)
        toks = _feedback_line_tokens(ln)
        if not toks:
            continue
        score = sum(freq[t] for t in set(toks)) + min(len(toks), 12) * 0.25
        ranked.append((score, ln))

    if not ranked:
        return ""

    ranked.sort(key=lambda x: x[0], reverse=True)
    points = [ln for _, ln in ranked[:max(1, min(4, max_points))]]

    # Aim for 3-4 bullets if possible.
    if len(points) < 3:
        for _, ln in ranked[len(points):]:
            if ln not in points:
                points.append(ln)
            if len(points) >= 3:
                break

    label = {
        "notes": "Notes quality",
        "mutation": "Note mutation",
        "doubts": "Doubt answers",
        "questions": "Quiz questions",
    }[target]

    return (
        "FEEDBACK-DRIVEN GUIDANCE (apply if relevant; do not mention feedback to student):\n"
        f"Area: {label}\n"
        + "\n".join(f"- {p}" for p in points[:4])
    )
