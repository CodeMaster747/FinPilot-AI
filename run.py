#!/usr/bin/env python3
"""FinPilot AI — one-command launcher.

    python3 run.py                  start the server (first run installs everything automatically)
    python3 run.py --tunnel         ... and also publish it through a Cloudflare tunnel for the phone
    python3 run.py reset            wipe local data and regenerate the demo
    python3 run.py test             run the backend tests
    python3 run.py build-frontend   rebuild the UI (needs Node.js; only for UI development)
    python3 run.py build-android    build the Android app (needs Node.js, JDK 21 and the Android SDK)
    python3 run.py install-android  install the Android app on a phone connected by USB (needs adb)

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


ANDROID = FRONTEND / "android"
APK = ANDROID / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
APP_ID = "ai.finpilot.app"


def android_sdk() -> Path | None:
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(var) and Path(os.environ[var]).is_dir():
            return Path(os.environ[var])
    local = ANDROID / "local.properties"
    if local.exists():
        for line in local.read_text().splitlines():
            if line.startswith("sdk.dir="):
                return Path(line.split("=", 1)[1].strip().replace("\\:", ":").replace("\\\\", "\\"))
    home = Path.home()
    for cand in (home / "Library/Android/sdk", home / "Android/Sdk", Path(os.environ.get("LOCALAPPDATA", home)) / "Android/Sdk"):
        if cand.is_dir():
            return cand
    return None


def java_major(java_home: Path) -> int:
    java = java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    try:
        out = subprocess.run([str(java), "-version"], capture_output=True, text=True, timeout=30).stderr
    except (OSError, subprocess.TimeoutExpired):
        return 0
    try:
        version = out.split('"')[1]
        return int(version.split(".")[1] if version.startswith("1.") else version.split(".")[0].split("-")[0])
    except (IndexError, ValueError):
        return 0


def find_jdk21() -> Path | None:
    """Capacitor 8's Android build needs JDK 21+: JAVA_HOME, the macOS registry, or Android Studio's bundled JBR."""
    candidates: list[Path] = []
    if os.environ.get("JAVA_HOME"):
        candidates.append(Path(os.environ["JAVA_HOME"]))
    if sys.platform == "darwin":
        try:
            found = subprocess.run(["/usr/libexec/java_home", "-v", "21"], capture_output=True, text=True, timeout=30).stdout.strip()
            if found:
                candidates.append(Path(found))
        except (OSError, subprocess.TimeoutExpired):
            pass
        candidates.append(Path("/Applications/Android Studio.app/Contents/jbr/Contents/Home"))
    elif os.name == "nt":
        candidates.append(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Android/Android Studio/jbr")
    else:
        candidates += [Path("/opt/android-studio/jbr"), Path.home() / "android-studio/jbr"]
    if shutil.which("java"):
        candidates.append(Path(shutil.which("java")).resolve().parent.parent)
    return next((c for c in candidates if c.is_dir() and java_major(c) >= 21), None)


def build_android() -> None:
    sdk = android_sdk()
    if sdk is None:
        sys.exit("Android SDK not found. Install Android Studio (it installs the SDK), or set ANDROID_HOME.")
    jdk = find_jdk21()
    if jdk is None:
        sys.exit("JDK 21 not found. Install it (for example from adoptium.net) or Android Studio, or set JAVA_HOME.")
    if not (ANDROID / "local.properties").exists():
        (ANDROID / "local.properties").write_text(f"sdk.dir={sdk.as_posix()}\n")
    npm, npx = shutil.which("npm"), shutil.which("npx")
    if npm is None or npx is None:
        sys.exit("Node.js/npm is required to build the Android app.")
    if not (FRONTEND / "node_modules").exists():
        say("Installing frontend packages (npm ci)…")
        if subprocess.call([npm, "ci", "--no-audit", "--no-fund"], cwd=FRONTEND) != 0:
            sys.exit("npm ci failed.")
    say("Building the UI (npm run build)…")
    if subprocess.call([npm, "run", "build"], cwd=FRONTEND) != 0:
        sys.exit("Frontend build failed.")
    say("Copying it into the Android project (npx cap sync android)…")
    if subprocess.call([npx, "cap", "sync", "android"], cwd=FRONTEND) != 0:
        sys.exit("Capacitor sync failed.")
    say(f"Building the APK with Gradle (JDK {java_major(jdk)} at {jdk})… the first build downloads Gradle and takes a few minutes.")
    gradlew = ANDROID / ("gradlew.bat" if os.name == "nt" else "gradlew")
    env = dict(os.environ, JAVA_HOME=str(jdk), ANDROID_HOME=str(sdk))
    if subprocess.call([str(gradlew), "assembleDebug", "--console=plain"], cwd=ANDROID, env=env) != 0:
        sys.exit("Gradle build failed (see the output above).")
    say(f"Built {APK.relative_to(ROOT)} ({APK.stat().st_size / 1e6:.0f} MB).")
    say("Install it on a phone connected by USB with:  python3 run.py install-android")


def find_adb() -> str | None:
    if shutil.which("adb"):
        return shutil.which("adb")
    sdk = android_sdk()
    adb = sdk / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb") if sdk else None
    return str(adb) if adb and adb.exists() else None


USB_HELP = """Connect the phone with a USB cable and turn on USB debugging:
    1. Settings → About phone → tap "Build number" 7 times (Xiaomi/POCO: "MIUI/OS version"; Samsung: Software information).
    2. Settings → System → Developer options → turn on "USB debugging"
       (Xiaomi/POCO/Redmi: also turn on "Install via USB").
    3. Plug the phone in, unlock it, and tap "Allow" on the "Allow USB debugging?" prompt.
  Then run  python3 run.py install-android  again."""


def install_android() -> None:
    adb = find_adb()
    if adb is None:
        sys.exit("adb not found. It comes with the Android SDK (platform-tools) — install Android Studio, or add platform-tools to PATH.")
    if not APK.exists():
        say("No APK yet — building it first.")
        build_android()
    out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=60).stdout
    devices = [line.split("\t") for line in out.splitlines()[1:] if "\t" in line]
    ready = [serial for serial, state in devices if state == "device"]
    if not ready:
        if any(state == "unauthorized" for _, state in devices):
            sys.exit("The phone is connected but hasn't allowed this computer yet: unlock it and tap \"Allow\" on the "
                     "\"Allow USB debugging?\" prompt, then run this again.")
        sys.exit("No phone found.\n  " + USB_HELP)
    serial = os.environ.get("ANDROID_SERIAL") or ready[0]
    if len(ready) > 1 and not os.environ.get("ANDROID_SERIAL"):
        say(f"Several devices are connected ({', '.join(ready)}); installing on {serial}. Set ANDROID_SERIAL to choose another.")
    say(f"Installing FinPilot AI on {serial}…")
    r = subprocess.run([adb, "-s", serial, "install", "-r", str(APK)], capture_output=True, text=True, timeout=600)
    output = (r.stdout + r.stderr).strip()
    if r.returncode != 0 or "Success" not in output:
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in output:
            sys.exit("An older FinPilot AI signed with a different key is installed. Uninstall it first with\n"
                     f"    {adb} -s {serial} uninstall {APP_ID}\n"
                     "  (your data stays on the server; the phone only forgets the server address and sign-in).")
        if "INSTALL_FAILED_USER_RESTRICTED" in output:
            sys.exit("The phone refused the install. On Xiaomi/POCO/Redmi, turn on Developer options → \"Install via USB\"; "
                     "on others, accept the prompt on the phone's screen, then try again.")
        sys.exit(f"Install failed:\n{output}")
    subprocess.run([adb, "-s", serial, "shell", "monkey", "-p", APP_ID, "-c", "android.intent.category.LAUNCHER", "1"],
                   capture_output=True, timeout=60)
    say("Installed and opened FinPilot AI on the phone. Next:")
    say("  1. Keep  python3 run.py  running on this computer (phone and computer on the same Wi-Fi or hotspot,")
    say("     or start it with --tunnel).")
    say("  2. In the app, scan the QR code the server printed (or type its address), then create your account.")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["build-frontend"]:
        build_frontend()
        return
    if args[:1] == ["build-android"]:
        build_android()
        return
    if args[:1] == ["install-android"]:
        install_android()
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
