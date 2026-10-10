"""In-process background jobs.

A small pool of daemon threads consumes job ids from a queue; every job is a row in ``jobs`` so the
UI can show progress. Before ``start()`` is called (tests, CLI) jobs run inline, synchronously.
"""

from __future__ import annotations

import logging
import queue
import threading
import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.session import session_scope
from app.models import Job

log = logging.getLogger("finpilot.jobs")

JobFn = Callable[["JobContext"], "dict[str, Any] | None"]
REGISTRY: dict[str, JobFn] = {}
LIVE_PROGRESS: dict[int, tuple[int, str | None]] = {}


def live_progress(job: Job) -> tuple[int, str | None]:
    """Progress for display: in-memory while running, the stored row otherwise."""
    if job.status == "running" and job.id in LIVE_PROGRESS:
        return LIVE_PROGRESS[job.id]
    return job.progress, job.message


def job(kind: str) -> Callable[[JobFn], JobFn]:
    def deco(fn: JobFn) -> JobFn:
        REGISTRY[kind] = fn
        return fn

    return deco


class JobContext:
    def __init__(self, runner: JobRunner, job_id: int, kind: str, user_id: int | None, params: dict[str, Any]):
        self.runner = runner
        self.job_id = job_id
        self.kind = kind
        self.user_id = user_id
        self.params = params

    def progress(self, pct: float, message: str | None = None) -> None:
        # In memory only: a job usually holds an open write transaction, and SQLite allows one writer.
        LIVE_PROGRESS[self.job_id] = (int(max(0, min(99, pct))), message)

    @property
    def stopping(self) -> bool:
        return self.runner.stopping.is_set()


class JobRunner:
    def __init__(self) -> None:
        self.q: queue.Queue[int] = queue.Queue()
        self.stopping = threading.Event()
        self.started = False
        self._lock = threading.Lock()

    # -- lifecycle -------------------------------------------------------------------------------
    def start(self, workers: int = 2) -> None:
        if self.started:
            return
        with session_scope() as db:
            db.execute(
                update(Job)
                .where(Job.status == "running")
                .values(status="interrupted", finished_at=utcnow(), message="App was restarted")
            )
            pending = db.scalars(select(Job.id).where(Job.status == "queued").order_by(Job.id)).all()
        for i in range(workers):
            threading.Thread(target=self._loop, name=f"finpilot-job-{i}", daemon=True).start()
        self.started = True
        for job_id in pending:
            self.q.put(job_id)

    def stop(self) -> None:
        self.stopping.set()

    # -- API -------------------------------------------------------------------------------------
    def enqueue(self, kind: str, user_id: int | None = None, params: dict[str, Any] | None = None, db: Session | None = None) -> int:
        """Queue a job. Pass the request's session as ``db`` whenever the caller has uncommitted changes:
        the job row then joins that transaction and the job starts only after it commits, so it sees the
        changes (and never waits on the caller's SQLite write lock from a second connection)."""
        if kind not in REGISTRY:
            raise KeyError(f"unknown job kind {kind}")
        params = params or {}
        if db is not None:
            job_id = self._insert(db, kind, user_id, params)
            event.listen(db, "after_commit", lambda _session: self._dispatch(job_id), once=True)
            return job_id
        with self._lock, session_scope() as own:
            job_id = self._insert(own, kind, user_id, params)
        self._dispatch(job_id)
        return job_id

    @staticmethod
    def _insert(db: Session, kind: str, user_id: int | None, params: dict[str, Any]) -> int:
        queued = db.scalars(
            select(Job).where(Job.kind == kind, Job.user_id.is_(user_id) if user_id is None else Job.user_id == user_id,
                              Job.status == "queued")
        ).all()
        for existing in queued:
            if existing.params == params:
                return existing.id
        row = Job(kind=kind, user_id=user_id, params=params, status="queued")
        db.add(row)
        db.flush()
        return row.id

    def _dispatch(self, job_id: int) -> None:
        if self.started:
            self.q.put(job_id)
        else:
            self.execute(job_id)

    # -- execution -------------------------------------------------------------------------------
    def _loop(self) -> None:
        while not self.stopping.is_set():
            try:
                job_id = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.execute(job_id)
            except Exception:  # pragma: no cover - defensive, execute() already records failures
                log.exception("job %s crashed", job_id)

    def execute(self, job_id: int) -> None:
        with session_scope() as db:
            row = db.get(Job, job_id)
            if row is None or row.status != "queued":
                return
            row.status = "running"
            row.started_at = utcnow()
            kind, user_id, params = row.kind, row.user_id, dict(row.params or {})
        ctx = JobContext(self, job_id, kind, user_id, params)
        status, error, result = "done", None, None
        try:
            result = REGISTRY[kind](ctx) or {}
        except Exception:
            log.exception("job %s (%s) failed", job_id, kind)
            status, error = "failed", traceback.format_exc()[-4000:]
        last = LIVE_PROGRESS.pop(job_id, (0, None))
        with session_scope() as db:
            values: dict[str, Any] = {"status": status, "finished_at": utcnow(), "result": result, "error": error,
                                      "progress": 100 if status == "done" else last[0], "message": last[1]}
            db.execute(update(Job).where(Job.id == job_id).values(**values))


runner = JobRunner()
