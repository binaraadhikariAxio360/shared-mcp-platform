"""Run locally: `python -m shared_mcp_server` (loopback only, see config.py).

Always a single process: replay protection for user assertions is in memory (auth/replay.py),
so multiple workers would need a shared replay store first.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from .apps_config import load_apps_file
from .config import ConfigError, load_settings
from .registry import RegistryError, build_registry
from .server import build_app


def main() -> int:
    try:
        settings = load_settings()
        registry = build_registry(load_apps_file(settings.apps_file))
    except (ConfigError, RegistryError) as exc:
        print(f"shared-mcp-server: configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=settings.log_level, format="%(message)s", stream=sys.stdout)
    uvicorn.run(
        build_app(settings, registry),
        host=settings.host,
        port=settings.port,
        workers=1,
        log_level=settings.log_level.lower(),
        proxy_headers=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
