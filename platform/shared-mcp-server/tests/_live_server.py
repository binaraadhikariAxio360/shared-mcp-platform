"""Runs the real ASGI app under uvicorn on 127.0.0.1 with an ephemeral port (tests only)."""

from __future__ import annotations

import threading
import time

import uvicorn

from shared_mcp_server.config import Settings
from shared_mcp_server.server import build_app


class LiveServer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings(port=0)
        self.app = build_app(self.settings)
        config = uvicorn.Config(self.app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.base_url = ""

    def __enter__(self) -> "LiveServer":
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            if time.monotonic() > deadline or not self._thread.is_alive():
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.02)
        port = self._server.servers[0].sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)
