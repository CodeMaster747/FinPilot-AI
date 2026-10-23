from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.security import ACCESS_COOKIE, decode_token
from app.db.session import get_db
from app.models import User


def bearer_token(request: Request) -> str | None:
    """The phone app sends `Authorization: Bearer <access token>`; the web app uses an httpOnly cookie."""
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return None


# The session commits when the endpoint returns, before the response is sent. (FastAPI's default "request" scope would
# commit after sending it, so a client acting on a response at once (reloading a list, or logging out right after
# deleting the account) could race the commit.) Every user of the session must share this one Depends to share a session.
SESSION = Depends(get_db, scope="function")


def _user_from_request(request: Request, db: Session) -> User | None:
    token = bearer_token(request) or request.cookies.get(ACCESS_COOKIE)
    payload = decode_token(token, "access") if token else None
    if not payload:
        return None
    return db.get(User, int(payload["sub"]))


def current_user(request: Request, db: Session = SESSION) -> User:
    user = _user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def optional_user(request: Request, db: Session = SESSION) -> User | None:
    return _user_from_request(request, db)


DB = Annotated[Session, SESSION]
CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
