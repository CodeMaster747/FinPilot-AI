#!/usr/bin/env python3
"""FinPilot AI — one-command launcher.

    python3 run.py            start the app (first run installs everything automatically)
    python3 run.py reset      wipe local data and regenerate the demo
    python3 run.py test       run the backend tests
    python3 run.py build-frontend   rebuild the UI (needs Node.js; only for UI development)

Needs only Python 3.11+. The first run creates a private virtual environment in .venv and
installs the pinned dependencies (internet needed once); after that everything runs offline.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "backend" / "requirements.txt"
FRONTEND = ROOT / "frontend"
MIN_PYTHON = (3, 11)


def say(msg: str) -> None:
    print(f"  {msg}", flush=True)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_environment() -> None:
    if sys.version_info < MIN_PYTHON:
        sys.exit(f"FinPilot AI needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ (found {sys.version.split()[0]}).")
    if not venv_python().exists():
        say("First run: creating a private Python environment (.venv)…")
        venv.EnvBuilder(with_pip=True).create(VENV)
    stamp = VENV / ".finpilot-requirements"
    digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text().strip() != digest:
        say("Installing dependencies (one time, needs internet — a few minutes)…")
        cmd = [str(venv_python()), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(REQUIREMENTS)]
        if subprocess.call(cmd) != 0:
            sys.exit("Dependency installation failed — check your internet connection and run again.")
        stamp.write_text(digest)


def build_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("Node.js/npm is required to rebuild the frontend (it is not needed to run the app).")
    say("Building the frontend (npm ci && npm run build)…")
    for args in (["ci", "--no-audit", "--no-fund"], ["run", "build"]):
        if subprocess.call([npm, *args], cwd=FRONTEND) != 0:
            sys.exit("Frontend build failed.")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["build-frontend"]:
        build_frontend()
        return
    ensure_environment()
    if not (FRONTEND / "out" / "index.html").exists():
        if shutil.which("npm"):
            build_frontend()
        else:
            say("Note: frontend/out is missing and Node.js is not installed — serving the API only.")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([str(venv_python()), "-m", "app.cli", *args], cwd=ROOT / "backend", env=env)
    while True:
        try:
            sys.exit(proc.wait())
        except KeyboardInterrupt:
            continue  # the app handles Ctrl+C itself and shuts down cleanly


if __name__ == "__main__":
    main()
