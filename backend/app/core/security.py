"""Password hashing (pwdlib + bcrypt) and JWT access/refresh tokens (PyJWT)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings

_hasher: PasswordHash | None = None
ALGORITHM = "HS256"
ACCESS_COOKIE = "fp_at"
REFRESH_COOKIE = "fp_rt"


def _password_hash() -> PasswordHash:
    global _hasher
    if _hasher is None:
        rounds = 4 if get_settings().testing else 12
        _hasher = PasswordHash((BcryptHasher(rounds=rounds),))
    return _hasher


def hash_password(password: str) -> str:
    return _password_hash().hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _password_hash().verify(password, hashed)
    except Exception:  # malformed hash
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: int) -> tuple[str, datetime]:
    settings = get_settings()
    exp = _now() + timedelta(minutes=settings.access_ttl_minutes)
    token = jwt.encode({"sub": str(user_id), "type": "access", "exp": exp}, settings.secret_key, ALGORITHM)
    return token, exp


def create_refresh_token(user_id: int, days: int | None = None) -> tuple[str, str, datetime]:
    settings = get_settings()
    jti = uuid.uuid4().hex
    exp = _now() + timedelta(days=days or settings.refresh_ttl_days)
    token = jwt.encode(
        {"sub": str(user_id), "type": "refresh", "jti": jti, "exp": exp}, settings.secret_key, ALGORITHM
    )
    return token, jti, exp


def decode_token(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
