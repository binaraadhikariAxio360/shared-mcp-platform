"""Environment-driven settings.

Step 2 serves an unauthenticated MCP endpoint, so the bind host is restricted to loopback.
Non-loopback binding is refused until authentication (Step 3) exists.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
DEFAULT_PROTOCOL_VERSION = "2025-11-25"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(ValueError):
    """Raised when the environment does not describe a safe, valid configuration."""


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8100
    protocol_version: str = DEFAULT_PROTOCOL_VERSION
    mcp_path: str = "/mcp"
    max_request_body_bytes: int = 256 * 1024
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.host not in LOOPBACK_HOSTS:
            raise ConfigError(
                f"MCP_SERVER_HOST={self.host!r} is not a loopback address; the unauthenticated "
                f"Step 2 server may only bind to {sorted(LOOPBACK_HOSTS)}"
            )
        if not 0 <= self.port <= 65535:
            raise ConfigError(f"MCP_SERVER_PORT={self.port} is out of range")
        if self.protocol_version not in HANDSHAKE_PROTOCOL_VERSIONS:
            raise ConfigError(
                f"MCP_PROTOCOL_VERSION={self.protocol_version!r} is not an initialize-handshake version "
                f"supported by the installed MCP SDK {list(HANDSHAKE_PROTOCOL_VERSIONS)}"
            )
        if not self.mcp_path.startswith("/") or self.mcp_path in ("/", "/healthz", "/readyz"):
            raise ConfigError(f"MCP_SERVER_PATH={self.mcp_path!r} is invalid")
        if not 1024 <= self.max_request_body_bytes <= 4 * 1024 * 1024:
            raise ConfigError("MCP_MAX_REQUEST_BODY_BYTES must be between 1024 and 4194304")
        if self.log_level not in LOG_LEVELS:
            raise ConfigError(f"MCP_LOG_LEVEL={self.log_level!r} must be one of {LOG_LEVELS}")


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer") from None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    defaults = Settings()
    return Settings(
        host=env.get("MCP_SERVER_HOST", defaults.host).strip(),
        port=_int(env, "MCP_SERVER_PORT", defaults.port),
        protocol_version=env.get("MCP_PROTOCOL_VERSION", defaults.protocol_version).strip(),
        mcp_path=env.get("MCP_SERVER_PATH", defaults.mcp_path).strip(),
        max_request_body_bytes=_int(env, "MCP_MAX_REQUEST_BODY_BYTES", defaults.max_request_body_bytes),
        log_level=env.get("MCP_LOG_LEVEL", defaults.log_level).strip().upper(),
    )
