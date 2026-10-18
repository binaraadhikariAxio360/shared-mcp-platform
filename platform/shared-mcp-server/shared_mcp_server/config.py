"""Environment-driven settings.

The bind host stays restricted to loopback until deployment hardening (Step 8), even though
every /mcp request is now authenticated (Step 3).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
DEFAULT_PROTOCOL_VERSION = "2025-11-25"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
AUDIENCE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
MAX_ASSERTION_LIFETIME_SECONDS = 60
MAX_CLOCK_SKEW_SECONDS = 5


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
    apps_file: str | None = None
    assertion_audience: str = "shared-mcp-server"
    assertion_max_lifetime_seconds: int = MAX_ASSERTION_LIFETIME_SECONDS
    clock_skew_seconds: int = MAX_CLOCK_SKEW_SECONDS
    replay_cache_max_entries: int = 50_000

    def __post_init__(self) -> None:
        if self.host not in LOOPBACK_HOSTS:
            raise ConfigError(
                f"MCP_SERVER_HOST={self.host!r} is not a loopback address; until deployment hardening "
                f"the server may only bind to {sorted(LOOPBACK_HOSTS)}"
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
        if not AUDIENCE_PATTERN.fullmatch(self.assertion_audience):
            raise ConfigError(f"MCP_ASSERTION_AUDIENCE={self.assertion_audience!r} is invalid")
        if not 1 <= self.assertion_max_lifetime_seconds <= MAX_ASSERTION_LIFETIME_SECONDS:
            raise ConfigError(f"MCP_ASSERTION_MAX_LIFETIME_SECONDS must be between 1 and {MAX_ASSERTION_LIFETIME_SECONDS}")
        if not 0 <= self.clock_skew_seconds <= MAX_CLOCK_SKEW_SECONDS:
            raise ConfigError(f"MCP_CLOCK_SKEW_SECONDS must be between 0 and {MAX_CLOCK_SKEW_SECONDS}")
        if not 100 <= self.replay_cache_max_entries <= 1_000_000:
            raise ConfigError("MCP_REPLAY_CACHE_MAX_ENTRIES must be between 100 and 1000000")


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
        apps_file=(env.get("MCP_APPS_FILE") or "").strip() or None,
        assertion_audience=env.get("MCP_ASSERTION_AUDIENCE", defaults.assertion_audience).strip(),
        assertion_max_lifetime_seconds=_int(
            env, "MCP_ASSERTION_MAX_LIFETIME_SECONDS", defaults.assertion_max_lifetime_seconds
        ),
        clock_skew_seconds=_int(env, "MCP_CLOCK_SKEW_SECONDS", defaults.clock_skew_seconds),
        replay_cache_max_entries=_int(env, "MCP_REPLAY_CACHE_MAX_ENTRIES", defaults.replay_cache_max_entries),
    )
