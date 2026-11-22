"""Starts BALANSE in its own window, without a browser address bar.

Used by the packaged Balanse.exe. For development, run:  python run_balanse.py
Data is kept in %APPDATA%\\Balanse so it survives installs and updates.
"""
from __future__ import annotations

import os
import random
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


def app_dir() -> Path:
    """Folder that holds app.py: the unpacked bundle when frozen, this folder otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # set by PyInstaller
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    folder = Path(os.environ.get("APPDATA", str(Path.home()))) / "Balanse"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def free_port(preferred: int) -> int:
    """A port nothing else is using. Checked on all addresses, the way Streamlit binds it."""
    with socket.socket() as probe:
        try:
            probe.bind(("", preferred))
            return preferred
        except OSError:
            probe.bind(("", 0))
            return probe.getsockname()[1]


def wait_for_server(port: int, server: threading.Thread, timeout: float = 60.0) -> bool:
    """True only when OUR server answers: the port must be ours and the server thread still alive."""
    deadline = time.time() + timeout
    while time.time() < deadline and server.is_alive():
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as reply:
                if reply.read().strip() == b"ok":
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def run_server(port: int) -> None:
    from streamlit.web import bootstrap

    # Streamlit wires Ctrl+C to the main thread. This server runs in a worker thread,
    # so skip that wiring; the window closing ends the program anyway.
    bootstrap._set_up_signal_handler = lambda *_args, **_kwargs: None
    # Keys are the command-line flag names. The streamlit command applies them before it
    # starts the server, and bootstrap.run does not, so apply them here first.
    flags = {
        "server_headless": True,
        "server_port": port,
        "server_address": "127.0.0.1",
        "browser_gatherUsageStats": False,
        "global_developmentMode": False,
    }
    bootstrap.load_config_options(flags)
    bootstrap.run(str(app_dir() / "app.py"), False, [], flags)


def main() -> None:
    os.chdir(app_dir())  # so Streamlit finds the bundled .streamlit folder
    os.environ.setdefault("BALANSE_LOCAL_DB", str(data_dir() / "balanse_local.db"))

    # A high port well away from 8501, which people often use for other Streamlit apps
    port = free_port(random.randint(49152, 65000))
    server = threading.Thread(target=run_server, args=(port,), daemon=True)
    server.start()
    if not wait_for_server(port, server):
        raise SystemExit("BALANSE could not start its local server.")

    import webview

    webview.create_window("BALANSE", f"http://127.0.0.1:{port}", width=1280, height=860, min_size=(900, 600))
    webview.start()


if __name__ == "__main__":
    main()
