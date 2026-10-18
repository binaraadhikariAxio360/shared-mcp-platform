"""Structured JSON audit log (one line per event, to stdout by default).

Every value passes through `redact` before it is written: credential-like keys are masked
and token-shaped strings are masked wherever they appear.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

REDACTED = "[REDACTED]"
MAX_STRING_LENGTH = 512
MAX_DEPTH = 6

SENSITIVE_KEY = re.compile(
    r"(authorization|token|secret|password|passwd|assertion|api[_-]?key|cookie|credential|private[_-]?key|session)",
    re.IGNORECASE,
)
SENSITIVE_VALUE = re.compile(
    r"(bearer\s+\S+"
    r"|eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"  # JWT
    r"|pcsess\.\S+"  # PractiCare session token
    r"|appr-[A-Za-z0-9_-]{8,}"  # PractiCare approval token
    r"|mcpsvc_[A-Za-z0-9_-]+"  # shared MCP service token
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"  # email address
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)
# Identifiers of credentials (never the credentials themselves); their values are still scanned.
SAFE_KEYS = frozenset({"token_id"})
MAX_ARG_KEYS = 32

_logger = logging.getLogger("shared_mcp_server.audit")


def redact(value: Any, _depth: int = 0) -> Any:
    if _depth > MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED
            if str(key) not in SAFE_KEYS and SENSITIVE_KEY.search(str(key))
            else redact(item, _depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item, _depth + 1) for item in value]
    if isinstance(value, str):
        masked = SENSITIVE_VALUE.sub(REDACTED, value)
        return masked if len(masked) <= MAX_STRING_LENGTH else masked[:MAX_STRING_LENGTH] + "...[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value), _depth + 1)


def arg_keys(arguments: Any) -> list[str]:
    """Top-level argument names only (never values), bounded for the audit log."""
    if not isinstance(arguments, Mapping):
        return []
    return sorted(str(key)[:64] for key in arguments)[:MAX_ARG_KEYS]


def audit_event(event: str, **fields: Any) -> dict[str, Any]:
    """Write one redacted audit record and return it (for tests)."""
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event}
    record.update(redact(fields))
    _logger.info(json.dumps(record, separators=(",", ":"), sort_keys=True, default=str))
    return record
