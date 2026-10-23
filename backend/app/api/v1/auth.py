"""Sign-up, sign-in and sessions.

The web app keeps its session in httpOnly cookies. The Android app (header `X-FinPilot-Client: android`) gets
the same JWTs in the response body instead, stores them on the phone and sends `Authorization: Bearer …`.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from datetime import timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.base import utcnow
from app.models import RefreshToken, User
from app.schemas.serialize import user_out
from app.services.users import create_user

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DOMAIN_RE = re.compile(r"^(?=.{3,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_attempts: dict[tuple[str, str], deque] = defaultdict(deque)
_lock = threading.Lock()


class Credentials(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=120)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    onboarded: bool | None = None
    preferences: dict[str, Any] | None = None


# numeric preferences and their allowed ranges; None clears an optional one
PREF_RANGES: dict[str, tuple[float, float]] = {
    "buffer_floor": (0, 1e8), "emergency_months": (1, 12), "retention_days": (7, 365), "wants_budget": (0, 1e8),
    "take_home_monthly": (0, 1e8), "payday": (1, 31), "rent_monthly": (0, 1e8), "rent_day": (1, 31),
}
INT_PREFS = {"emergency_months", "retention_days", "payday", "rent_day"}
OPTIONAL_PREFS = {"wants_budget", "take_home_monthly", "payday", "rent_monthly", "rent_payee", "rent_day"}
ALLOWED_PREFS = set(PREF_RANGES) | {"rent_payee", "extra_email_domains"}
# changing these changes the forecast, safe-to-spend or categories, so analytics are refreshed
ANALYTICS_PREFS = {"buffer_floor", "emergency_months", "wants_budget", "take_home_monthly", "payday", "rent_monthly", "rent_payee",
                   "rent_day"}


def _clean_pref(key: str, value: Any) -> Any:
    if value is None and key in OPTIONAL_PREFS:
        return None
    if key == "rent_payee":
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 120:
            raise HTTPException(422, "Landlord name must be 2–120 characters.")
        return value.strip()
    if key == "extra_email_domains":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HTTPException(422, "extra_email_domains must be a list of domains")
        out = []
        for v in value[:30]:
            d = v.strip().lower().lstrip("@").removeprefix("www.")
            if not DOMAIN_RE.match(d):
                raise HTTPException(422, f"'{v}' is not a valid email domain (example: mybank.co.in)")
            if d not in out:
                out.append(d)
        return out
    lo, hi = PREF_RANGES[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise HTTPException(422, f"{key} must be a number between {lo:g} and {hi:g}")
    return int(value) if key in INT_PREFS else value


LIMITS = {"login_failed": 10, "register": 30}  # per client address, per 5 minutes


def _recent(bucket: str, request: Request) -> deque:
    q = _attempts[(bucket, request.client.host if request.client else "local")]
    now = time.time()
    while q and now - q[0] > 300:
        q.popleft()
    return q


def _check_limit(bucket: str, request: Request) -> None:
    with _lock:
        if len(_recent(bucket, request)) >= LIMITS[bucket]:
            raise HTTPException(429, "Too many attempts. Please wait a few minutes.")


def _count(bucket: str, request: Request) -> None:
    with _lock:
        _recent(bucket, request).append(time.time())


def is_native(request: Request) -> bool:
    return request.headers.get("x-finpilot-client", "").lower() == "android"


def start_session(response: Response, db: Session, user: User, native: bool = False) -> dict[str, Any]:
    """Issue an access + refresh token pair: as cookies for the web app, in the body for the phone app."""
    settings = get_settings()
    access, _ = create_access_token(user.id)
    refresh, jti, exp = create_refresh_token(user.id, settings.native_refresh_ttl_days if native else None)
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp.astimezone(timezone.utc).replace(tzinfo=None)))
    if native:
        return {"access_token": access, "refresh_token": refresh, "expires_in": settings.access_ttl_minutes * 60}
    response.set_cookie(ACCESS_COOKIE, access, httponly=True, samesite="lax", secure=False,
                        max_age=settings.access_ttl_minutes * 60, path="/")
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, samesite="lax", secure=False,
                        max_age=settings.refresh_ttl_days * 86400, path="/api/v1/auth")
    return {}


def end_session(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


def _refresh_token_from(request: Request, body: dict[str, Any] | None) -> str | None:
    token = (body or {}).get("refresh_token") if isinstance(body, dict) else None
    return token if isinstance(token, str) and token else request.cookies.get(REFRESH_COOKIE)


@router.post("/register")
def register(body: Registration, response: Response, request: Request, db: DB) -> dict:
    _check_limit("register", request)
    _count("register", request)
    email = body.email.lower().strip()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(422, "Use a password with at least 8 characters.")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = create_user(db, email, body.name, body.password)
    return user_out(user) | start_session(response, db, user, is_native(request))


@router.post("/login")
def login(body: Credentials, response: Response, request: Request, db: DB) -> dict:
    _check_limit("login_failed", request)  # only failed attempts count, so a typo-prone user isn't locked out
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        _count("login_failed", request)
        raise HTTPException(401, "Wrong email or password.")
    return user_out(user) | start_session(response, db, user, is_native(request))


@router.post("/demo")
def demo_login(response: Response, request: Request, db: DB) -> dict:
    """The labelled demo account (sample data for presentations)."""
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == settings.demo_email))
    if user is None or user.data_end_date is None:
        raise HTTPException(503, "The demo is still being prepared — this takes about a minute on first start.")
    return user_out(user) | start_session(response, db, user, is_native(request))


@router.post("/refresh")
def refresh(request: Request, response: Response, db: DB, body: dict[str, Any] | None = Body(default=None)) -> dict:
    token = _refresh_token_from(request, body)
    payload = decode_token(token, "refresh") if token else None
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"])) if payload else None
    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        end_session(response)
        raise HTTPException(401, "Session expired — please sign in again.")
    # Rotate: every refresh token works once. The conditional UPDATE means two simultaneous refreshes with the same
    # token can't both succeed.
    used = db.execute(update(RefreshToken).where(RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None))
                      .values(revoked_at=utcnow())).rowcount
    if used != 1:
        raise HTTPException(401, "Session expired — please sign in again.")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, "Session expired — please sign in again.")
    return {"ok": True} | start_session(response, db, user, is_native(request))


@router.post("/logout")
def logout(request: Request, response: Response, db: DB, body: dict[str, Any] | None = Body(default=None)) -> dict:
    token = _refresh_token_from(request, body)
    payload = decode_token(token, "refresh") if token else None
    if payload:  # a bulk UPDATE, so a token already deleted (with its account, or by a demo reset) is simply skipped
        db.execute(update(RefreshToken).where(RefreshToken.jti == payload["jti"], RefreshToken.revoked_at.is_(None))
                   .values(revoked_at=utcnow()))
    end_session(response)
    return {"ok": True}


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return user_out(user)


@router.patch("/me")
def update_me(body: ProfileUpdate, db: DB, user: CurrentUser) -> dict:
    if body.name is not None:
        user.name = body.name.strip() or user.name
    if body.onboarded is not None:
        user.onboarded = body.onboarded
    if body.preferences:
        prefs = dict(user.preferences or {})
        changed = set()
        for k, v in body.preferences.items():
            if k in ALLOWED_PREFS:
                v = _clean_pref(k, v)
                if prefs.get(k) != v:
                    prefs[k] = v
                    changed.add(k)
        user.preferences = prefs
        if "rent_payee" in changed:
            from app.services.profile import apply_rent_rule

            apply_rent_rule(db, user, prefs.get("rent_payee"))
        if changed & ANALYTICS_PREFS:
            from app.jobs.runner import runner

            runner.enqueue("user_analytics", user_id=user.id, db=db)
    return user_out(user)
