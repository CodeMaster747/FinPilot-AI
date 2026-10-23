"""How the phone app finds this laptop: local-network addresses, an optional Cloudflare tunnel, and QR codes.

The phone and the laptop are usually on the same Wi-Fi (or the laptop joins the phone's hotspot), so the app
talks to http://<laptop-ip>:<port>. When a network keeps devices apart (common on college Wi-Fi),
`python3 run.py --tunnel` publishes the server at a temporary https://*.trycloudflare.com address instead.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger("finpilot.network")

TUNNEL_URL = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")


@dataclass
class Pairing:
    port: int = 8000
    lan_urls: list[str] = field(default_factory=list)
    tunnel_url: str | None = None
    tunnel_error: str | None = None

    @property
    def best_url(self) -> str | None:
        return self.tunnel_url or (self.lan_urls[0] if self.lan_urls else None)

    def as_dict(self) -> dict:
        return {"port": self.port, "lan_urls": self.lan_urls, "tunnel_url": self.tunnel_url,
                "tunnel_error": self.tunnel_error, "best_url": self.best_url}


PAIRING = Pairing()


def _usable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version != 4 or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_unspecified:
        return False
    return addr.is_private or ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")


def lan_addresses() -> list[str]:
    """IPv4 addresses other devices on the local network can use to reach this machine, best guess first."""
    found: list[str] = []
    # The address the OS would use for outbound traffic (no packet is actually sent).
    for probe in ("10.255.255.255", "192.168.255.255", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 1))
                ip = s.getsockname()[0]
            if _usable(ip) and ip not in found:
                found.append(ip)
        except OSError:
            continue
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if _usable(ip) and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def qr_terminal(text: str) -> str:
    """A QR code drawn with block characters, for the terminal."""
    import io

    import segno

    buf = io.StringIO()
    segno.make(text, error="m").terminal(out=buf, compact=True, border=2)
    return buf.getvalue()


def qr_svg(text: str) -> str:
    import io

    import segno

    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=6, border=2, dark="#111827", light="#ffffff", xmldecl=False)
    return buf.getvalue().decode()


class Tunnel:
    """A Cloudflare quick tunnel (no account needed) in front of the local server."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.url: str | None = None

    def start(self, timeout: float = 45) -> str:
        exe = shutil.which("cloudflared")
        if exe is None:
            raise RuntimeError("cloudflared is not installed. On macOS: brew install cloudflared "
                               "(Windows/Linux: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)")
        self.proc = subprocess.Popen(
            [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        found = threading.Event()

        def _read() -> None:
            assert self.proc and self.proc.stderr
            for line in self.proc.stderr:
                m = TUNNEL_URL.search(line)
                if m and not self.url:
                    self.url = m.group(0)
                    found.set()

        threading.Thread(target=_read, name="cloudflared-log", daemon=True).start()
        deadline = time.monotonic() + timeout
        while not found.is_set() and time.monotonic() < deadline:
            if self.proc.poll() is not None:
                break
            found.wait(0.25)
        if not self.url:
            self.stop()
            log.warning("cloudflared did not report a tunnel address within %.0f s", timeout)
            raise RuntimeError("cloudflared did not report a tunnel address — check your internet connection.")
        log.info("tunnel ready: %s → http://127.0.0.1:%s", self.url, self.port)
        return self.url

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self.proc.kill()
