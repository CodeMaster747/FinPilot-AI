"""Field-level encryption for raw message bodies (Fernet: AES-128-CBC + HMAC-SHA256)."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_fernet: Fernet | None = None


def _f() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_settings().fernet_key.encode())
    return _fernet


def encrypt_text(text: str) -> bytes:
    return _f().encrypt(text.encode("utf-8"))


def decrypt_text(blob: bytes | None) -> str | None:
    if not blob:
        return None
    try:
        return _f().decrypt(blob).decode("utf-8")
    except InvalidToken:
        return None
