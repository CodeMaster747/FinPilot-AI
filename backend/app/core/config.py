"""Runtime configuration.

Everything has a working default so the app runs with zero configuration. Secrets are generated
on first run into ``data/secret.json``; ports can be overridden with environment variables and are
swapped for free ones automatically by the server if busy.
"""

from __future__ import annotations

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_OUT_DIR = ROOT_DIR / "frontend" / "out"
SAMPLES_DIR = ROOT_DIR / "samples"
APP_VERSION = "1.0.0"


class Settings(BaseModel):
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    store_port: int = 8090
    secret_key: str
    fernet_key: str
    access_ttl_minutes: int = 30
    refresh_ttl_days: int = 14
    demo_email: str = "demo@finpilot.ai"
    demo_password: str = "demo1234"
    demo_name: str = "Aarav Sharma"
    raw_retention_days: int = 90
    job_workers: int = 2
    enable_scheduler: bool = True
    testing: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "finpilot.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def store_base_url(self) -> str:
        """URL the crawler uses to reach the bundled demo storefronts."""
        return f"http://{self.host}:{self.store_port}"

    @property
    def public_store_url(self) -> str:
        """URL the browser uses for product links."""
        return f"http://localhost:{self.store_port}"


def _load_or_create_secrets(data_dir: Path) -> dict[str, str]:
    path = data_dir / "secret.json"
    if path.exists():
        return json.loads(path.read_text())
    data = {"secret_key": secrets.token_urlsafe(48), "fernet_key": Fernet.generate_key().decode()}
    path.write_text(json.dumps(data))
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - Windows
        pass
    return data


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.environ.get("FINPILOT_DATA_DIR", ROOT_DIR / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("uploads", "models"):
        (data_dir / sub).mkdir(exist_ok=True)
    secret = _load_or_create_secrets(data_dir)
    return Settings(
        data_dir=data_dir,
        secret_key=secret["secret_key"],
        fernet_key=secret["fernet_key"],
        port=int(os.environ.get("FINPILOT_PORT", "8000")),
        store_port=int(os.environ.get("FINPILOT_STORE_PORT", "8090")),
        enable_scheduler=os.environ.get("FINPILOT_SCHEDULER", "1") == "1",
        testing=os.environ.get("FINPILOT_TESTING") == "1",
    )
