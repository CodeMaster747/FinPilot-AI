"""Runs the app (API + frontend) in one process. By default it also listens on the local network so the
FinPilot Android app can reach this laptop; `--local-only` keeps it on loopback."""

from __future__ import annotations

import asyncio
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


def bind_sockets(preferred: int, lan: bool = False) -> tuple[int, list[socket.socket]]:
    """Bind IPv4 and IPv6 (so 'localhost' always reaches us): loopback only, or every interface when `lan`.
    Falls forward to the next free port if the preferred one is busy."""
    v4_host, v6_host = ("0.0.0.0", "::") if lan else ("127.0.0.1", "::1")
    for port in range(preferred, preferred + 40):
        v4 = _bind(socket.AF_INET, v4_host, port)
        if v4 is None:
            continue
        socks = [v4]
        if socket.has_ipv6:
            v6 = _bind(socket.AF_INET6, v6_host, port)
            if v6 is None:
                # Something else owns the IPv6 side of this port, so 'localhost' could reach the wrong app.
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


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("uvicorn.error", "uvicorn.access", "httpx", "cmdstanpy", "prophet", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.ERROR)  # its one-time "building the font cache" notice is expected


def _print_banner(url: str, demo_email: str, demo_password: str) -> None:
    from app.core.network import PAIRING, qr_terminal

    print()
    print("  FinPilot AI is starting…")
    print(f"  On this computer:  {url}")
    if PAIRING.tunnel_url:
        print(f"  Phone (anywhere):  {PAIRING.tunnel_url}   ← Cloudflare tunnel")
    for lan_url in PAIRING.lan_urls:
        print(f"  Phone (same Wi-Fi or hotspot):  {lan_url}")
    if PAIRING.tunnel_error:
        print(f"  Tunnel not started: {PAIRING.tunnel_error}")
    best = PAIRING.best_url
    if best:
        print()
        print("  Pair the FinPilot app: open it on your phone and scan this code (or type the address above).")
        print(qr_terminal(best))
    elif get_settings().lan:
        print("  No local network found — connect this computer to Wi-Fi (or your phone's hotspot) to use the phone app.")
    print(f"  Demo account:  {demo_email} / {demo_password}  (sample data, for presentations)")
    print("  Stop:          Ctrl+C")
    print()


def serve(open_browser: bool = True, tunnel: bool = False) -> None:
    _configure_logging()
    settings = get_settings()
    from app.core import instance, network

    existing = instance.running_instance()
    if existing:
        print(f"\n  FinPilot AI is already running at {existing} — opening it.")
        print("  (To restart it, stop it first with Ctrl+C in the window where it runs.)\n")
        if open_browser:
            webbrowser.open(existing)
        return
    settings.port, main_socks = bind_sockets(settings.port, lan=settings.lan)

    from app.db.migrate import run_migrations
    from app.main import create_app

    run_migrations()
    from app.db.session import session_scope
    from app.services.reference_data import ensure_reference_data

    with session_scope() as db:  # categories and the merchant list exist before anyone can sign up
        ensure_reference_data(db)
    url = f"http://localhost:{settings.port}"
    instance.register(url)

    network.PAIRING.port = settings.port
    if settings.lan:
        network.PAIRING.lan_urls = [f"http://{ip}:{settings.port}" for ip in network.lan_addresses()]
    cloudflare: network.Tunnel | None = None
    if tunnel:
        cloudflare = network.Tunnel(settings.port)
        try:
            print("  Starting the Cloudflare tunnel…", flush=True)
            network.PAIRING.tunnel_url = cloudflare.start()
        except RuntimeError as exc:
            network.PAIRING.tunnel_error = str(exc)
            cloudflare = None

    main_server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning", access_log=False))
    _print_banner(url, settings.demo_email, settings.demo_password)

    def _open_when_ready() -> None:
        for _ in range(200):
            if main_server.started:
                if open_browser:
                    webbrowser.open(url)
                return
            time.sleep(0.1)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    try:
        asyncio.run(main_server.serve(sockets=main_socks))
    except KeyboardInterrupt:
        pass
    finally:
        if cloudflare:
            cloudflare.stop()
        instance.unregister()
    print("\n  FinPilot AI stopped.")
