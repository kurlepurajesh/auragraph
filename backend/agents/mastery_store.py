"""
agents/mastery_store.py  — SQLite-backed replacement for mock_cosmos.py

Stores per-user concept mastery graphs in the shared auragraph.db instead of
per-user JSON files. Provides the same public API as mock_cosmos.py so
call-sites can be updated with a one-line import change.

Tables:
  mastery_nodes  — per-user concept nodes (mastery status, position, mutation count)
  mastery_edges  — per-user concept graph edges

Public API (drop-in compatible with mock_cosmos):
  get_db(username)                                  → dict with "nodes" and "edges"
  save_db(db, username)                             → None
  increment_mutation_count(node_label, username)    → None
  update_node_status(node_label, new_status, username) → node dict | None
"""

from __future__ import annotations
import logging
import sqlite3

from contextlib import contextmanager
from pathlib import Path
from typing import Optional

logger = logging.getLogger("auragraph")

DB_PATH = Path(__file__).parent.parent / "auragraph.db"

# ── Default graph (same as the old DEFAULT_NODES/EDGES) ──────────────────────

_DEFAULT_NODES = [
    {"id": 1, "label": "Fourier Transform",   "status": "mastered",   "x": 50, "y": 18, "mutation_count": 0},
    {"id": 2, "label": "Convolution Theorem", "status": "struggling", "x": 50, "y": 44, "mutation_count": 0},
    {"id": 3, "label": "LTI Systems",          "status": "partial",    "x": 20, "y": 70, "mutation_count": 0},
    {"id": 4, "label": "Freq. Response",       "status": "mastered",   "x": 80, "y": 70, "mutation_count": 0},
    {"id": 5, "label": "Z-Transform",          "status": "partial",    "x": 50, "y": 90, "mutation_count": 0},
]
_DEFAULT_EDGES = [[1, 2], [2, 3], [2, 4], [3, 5], [4, 5]]


# ── DB helpers ────────────────────────────────────────────────────────────────

@contextmanager
def _conn():
    con = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _init_tables() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS mastery_nodes (
                user_id        TEXT    NOT NULL,
                node_id        INTEGER NOT NULL,
                label          TEXT    NOT NULL,
                status         TEXT    NOT NULL DEFAULT 'partial',
                x              REAL    NOT NULL DEFAULT 50,
                y              REAL    NOT NULL DEFAULT 50,
                mutation_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS mastery_edges (
                user_id  TEXT    NOT NULL,
                from_id  INTEGER NOT NULL,
                to_id    INTEGER NOT NULL,
                PRIMARY KEY (user_id, from_id, to_id)
            );
            CREATE INDEX IF NOT EXISTS idx_mastery_nodes_user ON mastery_nodes(user_id);
            CREATE INDEX IF NOT EXISTS idx_mastery_edges_user ON mastery_edges(user_id);
        """)
    logger.debug("mastery_store tables ready")


_init_tables()


# ── Migration from existing JSON files ───────────────────────────────────────

def migrate_json_files() -> int:
    """
    One-shot migration: find all mock_db_*.json files in the backend directory
    and import them into SQLite. Each file is renamed to *.migrated afterwards.
    Returns the number of users migrated.
    """
    import json, re
    backend_dir = Path(__file__).parent.parent
    migrated = 0
    for jf in backend_dir.glob("mock_db_*.json"):
        username_match = re.match(r"mock_db_(.+)\.json$", jf.name)
        if not username_match:
            continue
        username = username_match.group(1)
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            _write_user_graph(username, data.get("nodes", []), data.get("edges", []))
            jf.rename(jf.with_suffix(".json.migrated"))
            migrated += 1
            logger.info("mastery_store: migrated %s", jf.name)
        except Exception as exc:
            logger.warning("mastery_store: failed to migrate %s: %s", jf.name, exc)
    return migrated


# ── Internal write helper ─────────────────────────────────────────────────────

def _write_user_graph(username: str, nodes: list[dict], edges: list[list]) -> None:
    with _conn() as con:
        # Nodes — upsert
        for n in nodes:
            con.execute(
                """
                INSERT INTO mastery_nodes (user_id, node_id, label, status, x, y, mutation_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, node_id) DO UPDATE SET
                    label          = excluded.label,
                    status         = excluded.status,
                    x              = excluded.x,
                    y              = excluded.y,
                    mutation_count = excluded.mutation_count
                """,
                (username, n["id"], n["label"], n.get("status", "partial"),
                 n.get("x", 50), n.get("y", 50), n.get("mutation_count", 0))
            )
        # Edges — replace all
        con.execute("DELETE FROM mastery_edges WHERE user_id=?", (username,))
        for e in edges:
            if len(e) >= 2:
                con.execute(
                    "INSERT OR IGNORE INTO mastery_edges (user_id, from_id, to_id) VALUES (?,?,?)",
                    (username, e[0], e[1])
                )


def _ensure_user_exists(username: str) -> None:
    """Seed with default graph if this user has no nodes yet."""
    with _conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM mastery_nodes WHERE user_id=?", (username,)
        ).fetchone()[0]
    if count == 0:
        _write_user_graph(username, [dict(n) for n in _DEFAULT_NODES],
                          [list(e) for e in _DEFAULT_EDGES])


# ── Public API ────────────────────────────────────────────────────────────────

def get_db(username: str = "anonymous") -> dict:
    """Return the mastery graph for *username*, seeding defaults if absent."""
    _ensure_user_exists(username)
    with _conn() as con:
        nodes = [
            {
                "id": r["node_id"],
                "label": r["label"],
                "status": r["status"],
                "x": r["x"],
                "y": r["y"],
                "mutation_count": r["mutation_count"],
            }
            for r in con.execute(
                "SELECT * FROM mastery_nodes WHERE user_id=? ORDER BY node_id", (username,)
            ).fetchall()
        ]
        edges = [
            [r["from_id"], r["to_id"]]
            for r in con.execute(
                "SELECT from_id, to_id FROM mastery_edges WHERE user_id=?", (username,)
            ).fetchall()
        ]
    return {"nodes": nodes, "edges": edges}


def save_db(db: dict, username: str = "anonymous") -> None:
    """Persist *db* for *username*."""
    _write_user_graph(username, db.get("nodes", []), db.get("edges", []))


def increment_mutation_count(node_label: str, username: str = "anonymous") -> None:
    """Increment the mutation_count for the node matching *node_label*. Silent no-op if not found."""
    _ensure_user_exists(username)
    with _conn() as con:
        con.execute(
            """
            UPDATE mastery_nodes
            SET mutation_count = mutation_count + 1
            WHERE user_id=? AND LOWER(label)=LOWER(?)
            """,
            (username, node_label)
        )


def update_node_status(node_label: str, new_status: str,
                       username: str = "anonymous") -> Optional[dict]:
    """Update status for the matching node. Returns the updated node dict or None."""
    _ensure_user_exists(username)
    with _conn() as con:
        con.execute(
            """
            UPDATE mastery_nodes SET status=?
            WHERE user_id=? AND LOWER(label)=LOWER(?)
            """,
            (new_status, username, node_label)
        )
        row = con.execute(
            """
            SELECT node_id, label, status, x, y, mutation_count
            FROM mastery_nodes WHERE user_id=? AND LOWER(label)=LOWER(?)
            """,
            (username, node_label)
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["node_id"],
        "label": row["label"],
        "status": row["status"],
        "x": row["x"],
        "y": row["y"],
        "mutation_count": row["mutation_count"],
    }
