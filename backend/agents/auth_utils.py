"""
Auth Utility — AuraGraph (SQLite v2)
Uses the shared auragraph.db. Token TTL = 7 days for real users.
Demo token is a fixed string validated by its known value.
"""
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

try:
    from passlib.hash import bcrypt as _bcrypt
    _USE_BCRYPT = True
except ImportError:  # graceful fallback if passlib not yet installed
    import hashlib as _hashlib
    _USE_BCRYPT = False
    logging.getLogger("auragraph").warning(
        "passlib not installed — falling back to SHA-256 (install passlib[bcrypt] for production)"
    )

logger = logging.getLogger("auragraph")
DB_PATH = Path(__file__).parent.parent / "auragraph.db"
TOKEN_TTL_SECONDS = 7 * 24 * 3600   # 7 days


@contextmanager
def _conn():
    con = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _init_users():
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id              TEXT PRIMARY KEY,
                email           TEXT UNIQUE NOT NULL,
                password_hash   TEXT NOT NULL,
                token           TEXT,
                token_issued_at REAL NOT NULL DEFAULT 0,
                name            TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_users_token ON users(token);
        """)
    _migrate_users_from_json()


def _migrate_users_from_json():
    import json
    json_path = Path(__file__).parent.parent / "users.json"
    done_path = Path(__file__).parent.parent / "users.json.migrated"
    if done_path.exists() or not json_path.exists():
        return
    try:
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        with _conn() as con:
            for u in rows:
                con.execute(
                    "INSERT OR IGNORE INTO users VALUES (?,?,?,?,?,?)",
                    (u["id"], u["email"], u.get("password_hash", ""),
                     u.get("token"), u.get("token_issued_at", 0),
                     u.get("name", u["email"].split("@")[0].capitalize()))
                )
        json_path.rename(done_path)
        logger.info("Migrated %d users JSON -> SQLite", len(rows))
    except Exception as exc:
        logger.warning("users.json migration failed: %s", exc)


def _hash_password(password: str) -> str:
    if _USE_BCRYPT:
        return _bcrypt.using(rounds=12).hash(password)
    # Fallback: SHA-256 (dev only)
    return _hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, stored_hash: str) -> bool:
    """Safe constant-time password verification supporting both bcrypt and SHA-256 hashes."""
    if stored_hash.startswith("$2"):   # bcrypt hash
        if _USE_BCRYPT:
            try:
                return _bcrypt.verify(password, stored_hash)
            except Exception:
                return False
        return False  # stored as bcrypt but passlib not available
    # Legacy SHA-256 hash
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


def register_user(email: str, password: str) -> Optional[dict]:
    uid = str(uuid.uuid4())
    token = str(uuid.uuid4())
    name = email.split("@")[0].capitalize()
    try:
        with _conn() as con:
            con.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?)",
                (uid, email, _hash_password(password), token, time.time(), name)
            )
    except sqlite3.IntegrityError:
        return None
    return {"id": uid, "email": email, "token": token, "name": name}


def login_user(email: str, password: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            return None
        new_token = str(uuid.uuid4())
        con.execute("UPDATE users SET token=?, token_issued_at=? WHERE id=?",
                    (new_token, time.time(), row["id"]))
    return {"id": row["id"], "email": row["email"],
            "token": new_token, "name": row["name"]}


_DEMO_USER = {
    "id":    "demo",
    "email": "demo@auragraph.local",
    "name":  "Demo Student",
    "token": "demo-token",
}


def validate_token(token: str) -> Optional[dict]:
    if token == "demo-token":
        return dict(_DEMO_USER)
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE token=?", (token,)).fetchone()
    if not row:
        return None
    if time.time() - row["token_issued_at"] > TOKEN_TTL_SECONDS:
        return None   # expired — user must re-login
    return {"id": row["id"], "email": row["email"],
            "token": row["token"], "name": row["name"]}


_init_users()
