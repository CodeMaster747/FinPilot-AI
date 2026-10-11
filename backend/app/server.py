"""Runs the app (API + frontend) and the demo storefronts in one process, on loopback only."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import threading
import time
import webbrowser

import uvicorn

from app.core.config import get_settings

log = logging.getLogger("finpilot")


def _bind(family: int, host: str, port: int) -> socket.socket | None:
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    return sock


def bind_sockets(preferred: int, avoid: set[int]) -> tuple[int, list[socket.socket]]:
    """Bind 127.0.0.1 (and ::1 when available, so 'localhost' always reaches us).
    Falls forward to the next free port if the preferred one is busy."""
    candidates = [p for p in range(preferred, preferred + 40) if p not in avoid]
    for port in candidates:
        v4 = _bind(socket.AF_INET, "127.0.0.1", port)
        if v4 is None:
            continue
        socks = [v4]
        if socket.has_ipv6:
            v6 = _bind(socket.AF_INET6, "::1", port)
            if v6 is None:
                # Something else owns [::1]:port, so 'localhost' could reach the wrong app.
                probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                ipv6_usable = True
                try:
                    probe.bind(("::1", 0))
                except OSError:
                    ipv6_usable = False
                finally:
                    probe.close()
                if ipv6_usable:
                    v4.close()
                    continue
            else:
                socks.append(v6)
        return port, socks
    raise RuntimeError(f"No free port found near {preferred}")


class _EmbeddedServer(uvicorn.Server):
    """Second server in the same loop: leaves Ctrl+C handling to the main server."""

    @contextlib.contextmanager
    def capture_signals(self):  # noqa: ANN201
        yield


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("uvicorn.error", "uvicorn.access", "httpx", "cmdstanpy", "prophet", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.ERROR)  # its one-time "building the font cache" notice is expected


def serve(open_browser: bool = True) -> None:
    _configure_logging()
    settings = get_settings()
    from app.core import instance

    existing = instance.running_instance()
    if existing:
        print(f"\n  FinPilot AI is already running at {existing} — opening it.")
        print("  (To restart it, stop it first with Ctrl+C in the window where it runs.)\n")
        if open_browser:
            webbrowser.open(existing)
        return
    settings.port, main_socks = bind_sockets(settings.port, set())
    settings.store_port, store_socks = bind_sockets(settings.store_port, {settings.port})

    from app.db.migrate import run_migrations
    from app.demo_store.app import create_store_app
    from app.main import create_app

    run_migrations()
    from app.db.session import session_scope
    from app.services.reference_data import ensure_reference_data

    with session_scope() as db:  # categories and the merchant list exist before anyone can sign up
        ensure_reference_data(db)
    url = f"http://localhost:{settings.port}"
    instance.register(url)

    main_server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning", access_log=False))
    store_server = _EmbeddedServer(uvicorn.Config(create_store_app(), log_level="warning", access_log=False))

    print()
    print("  FinPilot AI is starting…")
    print(f"  App:          {url}")
    print(f"  Demo stores:  http://localhost:{settings.store_port}")
    print(f"  Demo login:   click 'Try the demo'  (or {settings.demo_email} / {settings.demo_password})")
    print("  Stop:         Ctrl+C")
    print()

    def _open_when_ready() -> None:
        for _ in range(200):
            if main_server.started:
                if open_browser:
                    webbrowser.open(url)
                return
            time.sleep(0.1)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    async def _run() -> None:
        store_task = asyncio.create_task(store_server.serve(sockets=store_socks))
        try:
            await main_server.serve(sockets=main_socks)
        finally:
            store_server.should_exit = True
            await store_task

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    finally:
        instance.unregister()
    print("\n  FinPilot AI stopped.")
