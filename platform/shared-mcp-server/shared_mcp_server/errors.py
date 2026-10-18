"""Normalized error codes and the security exception shared by the auth and server layers.

Error bodies sent to callers carry only a code and a correlation id. The precise reason for a
security decision goes to the audit log, never to the caller.
"""

from __future__ import annotations

ERROR_CODES = frozenset(
    {
        "UNAUTHENTICATED",
        "FORBIDDEN",
        "VALIDATION_ERROR",
        "NOT_FOUND",
        "MCP_UNAVAILABLE",
        "TIMEOUT",
        "UPSTREAM_ERROR",
    }
)

# JSON-RPC error codes used on the wire.
JSONRPC_UNAUTHENTICATED = -32001  # implementation-defined server error range
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


class McpSecurityError(Exception):
    """A request was refused. `code` is sent to the caller, `reason` is audit-only."""

    def __init__(self, code: str, reason: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
