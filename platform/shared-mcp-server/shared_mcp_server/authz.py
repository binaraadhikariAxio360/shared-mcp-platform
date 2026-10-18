"""Coarse, deny-by-default tool authorization on the shared server.

A caller sees a tool only if the tool belongs to the authenticated app, the verified role is in
the tool's allowlist, and the role is not excluded. Discovery and direct invocation use the same
function, so a tool that is not listed cannot be called either. Fine-grained permissions and
object-level policy stay in the application (PractiCare's Tool Gateway is the final authority).
"""

from __future__ import annotations

from .registry import EXCLUDED_ROLES, Registry, ToolManifest

__all__ = ["EXCLUDED_ROLES", "resolve_callable_tool", "visible_tools"]


def visible_tools(registry: Registry, app_id: str, role: str) -> list[ToolManifest]:
    if role in EXCLUDED_ROLES:
        return []
    return [tool for tool in registry.tools_for_app(app_id) if role in tool.allowed_roles]


def resolve_callable_tool(registry: Registry, app_id: str, role: str, name: str) -> ToolManifest | None:
    """The tool if this caller may invoke it; None for hidden, forbidden and unknown alike."""
    return next((tool for tool in visible_tools(registry, app_id, role) if tool.name == name), None)
