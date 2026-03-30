from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import PROJECT_ROOT, logger
from backend.models import User

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


def _load_legacy_users() -> dict[str, Any]:
    if not USERS_FILE.exists():
        return {}
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _find_user_by_username(db: Session, username: str) -> User | None:
    return (
        db.query(User)
        .filter(func.lower(User.username) == username.strip().lower())
        .first()
    )


def get_user_by_username(db: Session, username: str) -> User | None:
    if not username:
        return None
    return _find_user_by_username(db, username)


def get_user_profile(user: User) -> dict[str, str]:
    return {
        "username": user.username,
        "display_name": user.display_name or user.username,
    }


def bootstrap_auth_data(db: Session) -> None:
    changed = False
    legacy_users = _load_legacy_users()
    existing_usernames = {
        str(username).strip().lower()
        for (username,) in db.query(User.username).all()
        if username
    }

    for username, payload in legacy_users.items():
        if not isinstance(payload, dict):
            continue
        normalized_username = str(payload.get("username") or username).strip()
        normalized_key = normalized_username.lower()
        if not normalized_username or normalized_key in existing_usernames:
            continue

        hashed_password = payload.get("hashed_password")
        raw_password = payload.get("password")
        if not hashed_password:
            if raw_password:
                hashed_password = pwd_context.hash(str(raw_password))
            elif normalized_username.lower() == "admin":
                hashed_password = pwd_context.hash("admin123")
            else:
                continue

        db.add(
            User(
                username=normalized_username,
                display_name=str(payload.get("display_name") or normalized_username),
                hashed_password=str(hashed_password),
                created_at=float(payload.get("created_at") or time.time()),
            )
        )
        existing_usernames.add(normalized_key)
        changed = True

    if "admin" not in existing_usernames:
        db.add(
            User(
                username="admin",
                display_name="Administrator",
                hashed_password=pwd_context.hash("admin123"),
                created_at=time.time(),
            )
        )
        existing_usernames.add("admin")
        changed = True
        logger.info("default admin account created in database (username=admin, password=admin123)")

    if changed:
        db.commit()


def register_user(db: Session, username: str, password: str, display_name: str = "") -> User | None:
    if _find_user_by_username(db, username) is not None:
        return None

    user = User(
        username=username.strip(),
        display_name=display_name.strip() or username.strip(),
        hashed_password=pwd_context.hash(password),
        created_at=time.time(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("user registered: %s", user.username)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = _find_user_by_username(db, username)
    if user is None:
        return None
    if not pwd_context.verify(password, user.hashed_password):
        return None
    return user


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None
        exp = payload.get("exp", 0)
        if time.time() > exp:
            return None
        return str(username)
    except JWTError:
        return None
