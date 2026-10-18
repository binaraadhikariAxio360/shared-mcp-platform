"""Interface every application adapter implements (no adapters exist in Step 2).

An adapter forwards an already-authorized tool call to its application's internal API.
It holds no business rules and makes no authorization decisions of its own.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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


class AdapterError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown adapter error code {code!r}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CallContext:
    correlation_id: str
    app_id: str
    tool_name: str


class AppAdapter(ABC):
    app_id: str

    @abstractmethod
    async def call_tool(self, arguments: Mapping[str, Any], context: CallContext) -> dict[str, Any]:
        """Execute `context.tool_name` in the application; raise `AdapterError` on failure."""
