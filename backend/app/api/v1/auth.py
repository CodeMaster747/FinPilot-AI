from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from datetime import timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
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
from app.services.demo import create_user

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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


ALLOWED_PREFS = {"picks_enabled", "buffer_floor", "emergency_months", "picks_weekly_cap", "retention_days",
                 "excluded_interest_categories", "wants_budget"}
# numeric preferences and their allowed ranges (None = may be cleared)
PREF_RANGES: dict[str, tuple[float, float]] = {"buffer_floor": (0, 1e8), "emergency_months": (1, 12), "picks_weekly_cap": (1, 30),
                                               "retention_days": (7, 365), "wants_budget": (0, 1e8)}
PICKS_PREFS = {"picks_enabled", "buffer_floor", "emergency_months", "picks_weekly_cap", "excluded_interest_categories", "wants_budget"}


def _clean_pref(key: str, value: Any) -> Any:
    if key == "picks_enabled":
        if not isinstance(value, bool):
            raise HTTPException(422, "picks_enabled must be true or false")
        return value
    if key == "excluded_interest_categories":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HTTPException(422, "excluded_interest_categories must be a list of category names")
        return value[:50]
    if value is None and key == "wants_budget":
        return None
    lo, hi = PREF_RANGES[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise HTTPException(422, f"{key} must be a number between {lo:g} and {hi:g}")
    return int(value) if key in ("emergency_months", "picks_weekly_cap", "retention_days") else value


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


def start_session(response: Response, db: Session, user: User) -> None:
    settings = get_settings()
    access, _ = create_access_token(user.id)
    refresh, jti, exp = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp.astimezone(timezone.utc).replace(tzinfo=None)))
    response.set_cookie(ACCESS_COOKIE, access, httponly=True, samesite="lax", secure=False,
                        max_age=settings.access_ttl_minutes * 60, path="/")
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, samesite="lax", secure=False,
                        max_age=settings.refresh_ttl_days * 86400, path="/api/v1/auth")


def end_session(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


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
    start_session(response, db, user)
    return user_out(user)


@router.post("/login")
def login(body: Credentials, response: Response, request: Request, db: DB) -> dict:
    _check_limit("login_failed", request)  # only failed attempts count, so a typo-prone user isn't locked out
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        _count("login_failed", request)
        raise HTTPException(401, "Wrong email or password.")
    start_session(response, db, user)
    return user_out(user)


@router.post("/demo")
def demo_login(response: Response, db: DB) -> dict:
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == settings.demo_email))
    if user is None or user.data_end_date is None:
        raise HTTPException(503, "The demo is still being prepared — this takes about a minute on first start.")
    start_session(response, db, user)
    return user_out(user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: DB) -> dict:
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"])) if payload else None
    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        end_session(response)
        raise HTTPException(401, "Session expired — please sign in again.")
    row.revoked_at = utcnow()  # rotate: every refresh token works once
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(401, "Session expired — please sign in again.")
    start_session(response, db, user)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: DB) -> dict:
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    if payload:
        row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
        if row:
            row.revoked_at = utcnow()
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
        if changed & PICKS_PREFS and prefs.get("picks_enabled"):
            from app.jobs.runner import runner

            runner.enqueue("refresh_picks", user_id=user.id, db=db)
    return user_out(user)
