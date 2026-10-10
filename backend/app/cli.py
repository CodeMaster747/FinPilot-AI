"""Entry point used by run.py:  python -m app.cli [serve|reset|test|migrate] [--no-browser]"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

USAGE = """usage: python3 run.py [command]

  (no command)     start FinPilot AI and open the browser
  reset            wipe all local data, regenerate the demo, then start
  test             run the backend test suite
  migrate          apply database migrations only
  --no-browser     don't open a browser window
"""


def _data_dir() -> Path:
    from app.core.config import ROOT_DIR

    return Path(os.environ.get("FINPILOT_DATA_DIR", ROOT_DIR / "data"))


def reset_data() -> None:
    data = _data_dir()
    for name in ("finpilot.db", "finpilot.db-wal", "finpilot.db-shm"):
        (data / name).unlink(missing_ok=True)
    for sub in ("uploads", "models"):
        shutil.rmtree(data / sub, ignore_errors=True)
    print("  Local data wiped — the demo will be regenerated.")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    flags = {a for a in args if a.startswith("-")}
    positional = [a for a in args if not a.startswith("-")]
    cmd = positional[0] if positional else "serve"

    if cmd in {"help", "-h", "--help"} or "--help" in flags:
        print(USAGE)
        return 0
    if cmd == "test":
        import pytest

        from app.core.config import BACKEND_DIR

        return pytest.main(["-q", "-p", "no:cacheprovider", str(BACKEND_DIR / "tests"), *positional[1:]])
    if cmd == "migrate":
        from app.db.migrate import run_migrations

        run_migrations()
        print("  Database is up to date.")
        return 0
    if cmd == "reset":
        from app.core.instance import running_instance

        if running_instance():
            print("  FinPilot AI is running — stop it first (Ctrl+C in its window), then run the reset again.")
            return 1
        reset_data()
        cmd = "serve"
    if cmd == "serve":
        from app.server import serve

        serve(open_browser="--no-browser" not in flags)
        return 0
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
