"""Interface every application adapter implements (no production adapters exist yet).

An adapter forwards an already-authorized tool call to its application's internal API.
It holds no business rules and makes no authorization decisions of its own: the application
re-verifies the forwarded assertion and remains the final authority for user, tenant and role.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..errors import ERROR_CODES

__all__ = ["ERROR_CODES", "AdapterError", "AppAdapter", "CallContext"]


class AdapterError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown adapter error code {code!r}")
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CallContext:
    """Built by the server only from the verified service credential and user assertion."""

    correlation_id: str
    app_id: str
    tool_name: str
    user_id: str
    tenant_id: str
    role: str
    # The verified assertion, kept for forwarding so the application can re-verify it.
    assertion: str = field(repr=False)


class AppAdapter(ABC):
    app_id: str

    @abstractmethod
    async def call_tool(self, arguments: Mapping[str, Any], context: CallContext) -> dict[str, Any]:
        """Execute `context.tool_name` in the application; raise `AdapterError` on failure."""
