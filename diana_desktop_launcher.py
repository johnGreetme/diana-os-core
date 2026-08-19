"""DIANA OS Telemetry — native desktop wrapper (pywebview + Streamlit).

Starts `dashboard/diana_monitor.py` as a headless Streamlit subprocess, waits
until the local server answers, then hosts it in a standalone desktop window.
On window close the Streamlit child is terminated so no orphan server remains.

Usage:
    python diana_desktop_launcher.py
    pythonw diana_desktop_launcher.py   # no console (Startup shortcut)
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import webview
except ImportError:
    sys.stderr.write(
        "[DIANA OS] pywebview is required. Install with:\n"
        "  pip install pywebview\n"
    )
    sys.exit(1)

WORKSPACE = Path(__file__).resolve().parent
DASHBOARD = WORKSPACE / "dashboard" / "diana_monitor.py"
HOST = "127.0.0.1"
PORT = int(os.environ.get("DIANA_DESKTOP_PORT", "8501"))
URL = f"http://{HOST}:{PORT}"
HEALTH_URL = f"{URL}/_stcore/health"
BOOT_TIMEOUT_SEC = 60
POLL_INTERVAL_SEC = 0.4

_streamlit_proc: subprocess.Popen | None = None
_we_started_server = False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _server_healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1.0) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    # Older Streamlit builds may not expose /_stcore/health — fall back to root.
    try:
        with urllib.request.urlopen(URL, timeout=1.0) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _python_for_subprocess() -> str:
    """Resolve python.exe when this launcher is started via pythonw.exe."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        candidate = exe.with_name("python.exe")
        if candidate.is_file():
            return str(candidate)
    return str(exe)


def _start_streamlit() -> subprocess.Popen:
    if not DASHBOARD.is_file():
        raise FileNotFoundError(f"Dashboard not found: {DASHBOARD}")

    creationflags = 0
    if sys.platform == "win32":
        # Hide the child console when launched via python.exe; pythonw has none.
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    cmd = [
        _python_for_subprocess(),
        "-m",
        "streamlit",
        "run",
        str(DASHBOARD),
        "--server.headless=true",
        f"--server.address={HOST}",
        f"--server.port={PORT}",
        "--browser.gatherUsageStats=false",
        "--server.fileWatcherType=none",
    ]

    return subprocess.Popen(
        cmd,
        cwd=str(WORKSPACE / "dashboard"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _wait_for_server(timeout: float = BOOT_TIMEOUT_SEC) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_healthy():
            return
        if _streamlit_proc is not None and _streamlit_proc.poll() is not None:
            raise RuntimeError(
                f"Streamlit exited early with code {_streamlit_proc.returncode}"
            )
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(
        f"Streamlit did not become ready at {URL} within {timeout}s"
    )


def _shutdown_streamlit() -> None:
    global _streamlit_proc, _we_started_server
    proc = _streamlit_proc
    if not _we_started_server or proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
    except OSError:
        pass
    finally:
        _streamlit_proc = None
        _we_started_server = False


def main() -> int:
    global _streamlit_proc, _we_started_server

    atexit.register(_shutdown_streamlit)

    already_up = _port_open(HOST, PORT) and _server_healthy()
    if not already_up:
        _streamlit_proc = _start_streamlit()
        _we_started_server = True
        _wait_for_server()
    else:
        # Reuse an existing local Streamlit instance; do not kill it on exit.
        _we_started_server = False

    # Shortcut .ico is set by install_diana_services.ps1; this pywebview
    # build has no create_window(icon=...) kwarg.
    window = webview.create_window(
        title="DIANA OS Telemetry",
        url=URL,
        width=1440,
        height=900,
        min_size=(960, 640),
        confirm_close=False,
    )

    try:
        webview.start()
    finally:
        _shutdown_streamlit()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — surface boot faults for pythonw users
        # pythonw has no console; drop a breadcrumb next to the launcher.
        try:
            log_path = WORKSPACE / "diana_desktop_launcher.log"
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} ERROR: {exc}\n")
        except OSError:
            pass
        raise
