"""
Mock Auth Utility — AuraGraph
Stores users in users.json with hashed passwords.
"""
import json, uuid, hashlib, os
from pathlib import Path

USERS_PATH = Path(__file__).parent.parent / "users.json"


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
        "name": email.split("@")[0].capitalize(),
    }
    users.append(user)
    _save_users(users)
    return {k: v for k, v in user.items() if k != "password_hash"}


def login_user(email: str, password: str) -> dict:
    users = _get_users()
    ph = _hash_password(password)
    user = next((u for u in users if u["email"] == email and u["password_hash"] == ph), None)
    if not user:
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


def validate_token(token: str) -> dict:
    users = _get_users()
    user = next((u for u in users if u.get("token") == token), None)
    if not user:
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}
