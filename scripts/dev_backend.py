"""Start the one supported local backend after an explicit port preflight."""

from __future__ import annotations

import socket
from pathlib import Path

import uvicorn

HOST = "127.0.0.1"
PORT = 8000
APP_DIR = Path(__file__).resolve().parents[1]


def assert_port_available() -> None:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.5):
            pass
    except (ConnectionRefusedError, TimeoutError, OSError):
        return
    else:
        raise SystemExit(
            "Port 8000 is already in use.\n"
            "Existing runtime may be Docker/WSL or another Uvicorn process.\n"
            "Stop the conflicting backend before starting LumiLab development server."
        )


def main() -> None:
    assert_port_available()
    uvicorn.run("src.main:app", host=HOST, port=PORT, reload=True, app_dir=str(APP_DIR))


if __name__ == "__main__":
    main()
