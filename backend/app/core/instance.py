"""One running app per data folder: a second launch finds the first and opens it instead of starting a rival
server (two job runners and schedulers on one SQLite file)."""

from __future__ import annotations

import json
import os
import urllib.request
import uuid

from app.core.config import get_settings

INSTANCE_ID = uuid.uuid4().hex


def _runtime_file():  # noqa: ANN202
    return get_settings().data_dir / "runtime.json"


def running_instance() -> str | None:
    """URL of an app already serving this data folder, if one answers its health check."""
    try:
        info = json.loads(_runtime_file().read_text())
        url, instance = info["url"], info["instance"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        with urllib.request.urlopen(f"{url}/api/v1/health", timeout=1.5) as res:  # noqa: S310 - loopback URL we wrote
            health = json.loads(res.read())
    except (OSError, ValueError):
        return None
    return url if health.get("instance") == instance else None


def register(url: str) -> None:
    _runtime_file().write_text(json.dumps({"url": url, "instance": INSTANCE_ID, "pid": os.getpid()}))


def unregister() -> None:
    try:
        if json.loads(_runtime_file().read_text()).get("instance") == INSTANCE_ID:
            _runtime_file().unlink()
    except (OSError, ValueError):
        pass
