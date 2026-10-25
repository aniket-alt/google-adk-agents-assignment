"""Start (and stop) the MCP Toolbox server for the storefront tools."""

import atexit
import os
import socket
import subprocess
import time

from .store_db import STORE_DIR, init_db

PORT = int(os.getenv("TOOLBOX_PORT", "5000"))
HOST = "127.0.0.1"
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLBOX_EXE = os.getenv("TOOLBOX_BIN", os.path.join(BASE_DIR, "bin", "toolbox.exe" if os.name == "nt" else "toolbox"))
URL = f"http://{HOST}:{PORT}"

_process: subprocess.Popen | None = None


def _is_listening() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def ensure_toolbox(timeout: float = 30.0) -> str:
    """Make sure the database exists and Toolbox is serving; returns its URL. Reuses a running server."""
    global _process
    init_db()
    if _is_listening():
        return URL
    if not os.path.isfile(TOOLBOX_EXE):
        raise FileNotFoundError(
            f"Toolbox binary not found at {TOOLBOX_EXE}. See the README for the download link, or set TOOLBOX_BIN."
        )
    # cwd is the store folder so tools.yaml can refer to the database as plain "store.db".
    _process = subprocess.Popen(
        [TOOLBOX_EXE, "--config", "tools.yaml", "--port", str(PORT), "--address", HOST, "--disable-version-check"],
        cwd=STORE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    atexit.register(stop_toolbox)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_listening():
            return URL
        if _process.poll() is not None:
            raise RuntimeError("Toolbox exited during startup; run it manually to see the error.")
        time.sleep(0.3)
    raise TimeoutError("Toolbox did not start in time.")


def stop_toolbox() -> None:
    global _process
    if _process and _process.poll() is None:
        _process.terminate()
    _process = None
