from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import PROJECT_ROOT, logger

USERS_FILE = PROJECT_ROOT / "users.json"
JWT_SECRET_FILE = PROJECT_ROOT / ".jwt_secret"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 86400  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_jwt_secret() -> str:
    if JWT_SECRET_FILE.exists():
        return JWT_SECRET_FILE.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    JWT_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


JWT_SECRET = _get_jwt_secret()


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_users(users: dict) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _ensure_default_admin() -> None:
    users = _load_users()
    if not users:
        users["admin"] = {
            "username": "admin",
            "display_name": "Administrator",
            "hashed_password": pwd_context.hash("admin123"),
            "created_at": time.time(),
        }
        _save_users(users)
        logger.info("default admin account created (username=admin, password=admin123)")


_ensure_default_admin()


def register_user(username: str, password: str, display_name: str = "") -> dict | None:
    users = _load_users()
    if username.lower() in {k.lower() for k in users}:
        return None
    users[username] = {
        "username": username,
        "display_name": display_name or username,
        "hashed_password": pwd_context.hash(password),
        "created_at": time.time(),
    }
    _save_users(users)
    logger.info("user registered: %s", username)
    return {"username": username, "display_name": display_name or username}


def authenticate_user(username: str, password: str) -> dict | None:
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    if not pwd_context.verify(password, user["hashed_password"]):
        return None
    return {"username": user["username"], "display_name": user.get("display_name", username)}


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            return None
        exp = payload.get("exp", 0)
        if time.time() > exp:
            return None
        return username
    except JWTError:
        return None


def get_user_profile(username: str) -> dict | None:
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    return {"username": user["username"], "display_name": user.get("display_name", username)}
