from __future__ import annotations

import sys
sys.dont_write_bytecode = True  # 禁止.pyc缓存，永远吃源码

import os
import socket
import threading
import time
import webbrowser

import uvicorn

from dialogue_eval.api.app import app


def _is_port_open(host: str, port: int) -> bool:
    """Probe whether the local API server is already accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def main() -> None:
    """Start the API server and open the browser after the socket becomes reachable."""
    host = os.getenv("DIALOGUE_EVAL_HOST", "127.0.0.1")
    port = int(os.getenv("DIALOGUE_EVAL_PORT", "8000"))
    url = f"http://{host}:{port}"

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(100):
        # Waiting for the port avoids opening the browser before uvicorn is ready.
        if _is_port_open(host, port):
            webbrowser.open(url)
            break
        time.sleep(0.1)

    thread.join()


if __name__ == "__main__":
    main()
