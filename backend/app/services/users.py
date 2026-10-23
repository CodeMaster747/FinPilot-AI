"""Creating accounts. Real users start with neutral defaults; only the demo account gets the persona's settings."""

from __future__ import annotations

from typing import Any

from app.core.security import hash_password
from app.models import User

DEFAULT_PREFERENCES: dict[str, Any] = {
    "buffer_floor": 10000,  # the smallest safety buffer; the real one is max(this, a month of must-pays)
    "emergency_months": 3,
    "retention_days": 90,  # original message text is deleted after this many days
}


def create_user(db, email: str, name: str, password: str, is_demo: bool = False,  # noqa: ANN001
                preferences: dict[str, Any] | None = None) -> User:
    user = User(email=email.lower().strip(), name=name.strip(), password_hash=hash_password(password), is_demo=is_demo,
                preferences=dict(preferences if preferences is not None else DEFAULT_PREFERENCES))
    db.add(user)
    db.flush()
    return user
