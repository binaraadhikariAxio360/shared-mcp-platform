"""Run locally: `python -m shared_mcp_server` (loopback only, see config.py)."""

from __future__ import annotations

import logging
import sys

import uvicorn

from .config import ConfigError, load_settings
from .server import build_app


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"shared-mcp-server: configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=settings.log_level, format="%(message)s", stream=sys.stdout)
    uvicorn.run(
        build_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
