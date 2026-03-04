"""
Mock Auth Utility — AuraGraph
Stores users in users.json with hashed passwords.
Tokens expire after TOKEN_TTL_SECONDS and are rotated on each login.
"""
import json, uuid, hashlib, time, os
from pathlib import Path

USERS_PATH = Path(__file__).parent.parent / "users.json"
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _get_users():
    if not USERS_PATH.exists():
        USERS_PATH.write_text(json.dumps([]))
    return json.loads(USERS_PATH.read_text())


def _save_users(users):
    USERS_PATH.write_text(json.dumps(users, indent=2))


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def register_user(email: str, password: str) -> dict:
    users = _get_users()
    if any(u["email"] == email for u in users):
        return None  # already exists
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": _hash_password(password),
        "token": str(uuid.uuid4()),
        "token_issued_at": time.time(),
        "name": email.split("@")[0].capitalize(),
    }
    users.append(user)
    _save_users(users)
    return {k: v for k, v in user.items() if k not in ("password_hash",)}


def login_user(email: str, password: str) -> dict:
    users = _get_users()
    ph = _hash_password(password)
    user = next((u for u in users if u["email"] == email and u["password_hash"] == ph), None)
    if not user:
        return None
    # Rotate token on every login
    user["token"] = str(uuid.uuid4())
    user["token_issued_at"] = time.time()
    _save_users(users)
    return {k: v for k, v in user.items() if k not in ("password_hash",)}


_DEMO_USER = {
    "id": "demo",
    "email": "demo@auragraph.local",
    "name": "Demo",
    "token": "demo-token",
    "token_issued_at": 0,  # never expires for demo
}

def validate_token(token: str) -> dict:
    # Allow demo-token so the frontend works without registration
    if token == "demo-token":
        return dict(_DEMO_USER)
    users = _get_users()
    user = next((u for u in users if u.get("token") == token), None)
    if not user:
        return None
    # Check expiry — tokens older than TOKEN_TTL_SECONDS are rejected
    issued_at = user.get("token_issued_at", 0)
    if time.time() - issued_at > TOKEN_TTL_SECONDS:
        return None  # expired; user must log in again
    return {k: v for k, v in user.items() if k not in ("password_hash",)}
