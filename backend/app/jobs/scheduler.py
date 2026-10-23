"""Recurring work: sync connected mailboxes, re-check wishlist prices, refresh nightly analytics, purge expired raw text."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.db.base import utcnow
from app.db.session import session_scope
from app.jobs.runner import runner
from app.models import Job

log = logging.getLogger("finpilot.scheduler")


@dataclass
class Task:
    kind: str
    every: timedelta
    params: dict = field(default_factory=dict)


TASKS = [
    Task("imap_sync_all", timedelta(minutes=30)),
    Task("wishlist_prices", timedelta(hours=24)),
    Task("nightly_all_users", timedelta(hours=24)),
    Task("retention_purge", timedelta(hours=24)),
]


class Scheduler:
    def __init__(self, grace_seconds: int = 300, tick_seconds: int = 30) -> None:
        self.grace = grace_seconds
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="finpilot-scheduler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Startup already runs the demo bootstrap and warm-up; give it time before checking schedules.
        if self._stop.wait(self.grace):
            return
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # pragma: no cover
                log.exception("scheduler tick failed")
            self._stop.wait(self.tick_seconds)

    def tick(self, now: datetime | None = None) -> list[str]:
        now = now or utcnow()
        fired = []
        with session_scope() as db:
            last_runs = dict(
                db.execute(
                    select(Job.kind, func.max(Job.created_at)).where(Job.kind.in_([t.kind for t in TASKS])).group_by(Job.kind)
                ).all()
            )
        for task in TASKS:
            last = last_runs.get(task.kind)
            if last is None or now - last >= task.every:
                runner.enqueue(task.kind, params=task.params)
                fired.append(task.kind)
        return fired


scheduler = Scheduler()

