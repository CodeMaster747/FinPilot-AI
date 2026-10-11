"""SQLite engine (WAL mode) and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

SessionLocal = sessionmaker(expire_on_commit=False, autoflush=False)
_engine: Engine | None = None


def _set_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def init_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    settings = get_settings()
    url = URL.create("sqlite", database=str(settings.db_path))
    _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30}, pool_size=10, max_overflow=20)
    event.listen(_engine, "connect", _set_pragmas)
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    return init_engine()


def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def session_scope() -> Iterator[Session]:
    init_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    init_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
