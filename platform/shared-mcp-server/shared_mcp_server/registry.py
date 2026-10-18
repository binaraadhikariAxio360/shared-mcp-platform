"""Application and tool registry (data only).

Applications and their tool manifests are declared as data and validated once at startup;
an invalid registry prevents the server from starting. Step 2 ships an empty registry.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]{1,31}$")
ROLE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
# Identity is resolved server-side from verified credentials, never from tool arguments.
FORBIDDEN_ARGUMENT_NAMES = frozenset(
    {"tenant_id", "tenant", "user_id", "user", "user_role", "role", "roles", "permissions"}
)


class RegistryError(ValueError):
    """Raised when an application or tool declaration is invalid."""


@dataclass(frozen=True)
class AppRegistration:
    app_id: str
    display_name: str


@dataclass(frozen=True)
class ToolManifest:
    name: str
    app_id: str
    description: str
    input_schema: Mapping[str, Any]
    allowed_roles: frozenset[str]
    output_schema: Mapping[str, Any] | None = None
    read_only: bool = True


@dataclass(frozen=True)
class Registry:
    apps: Mapping[str, AppRegistration] = field(default_factory=dict)
    tools: Mapping[str, ToolManifest] = field(default_factory=dict)

    def tools_for_app(self, app_id: str) -> list[ToolManifest]:
        return [tool for tool in self.tools.values() if tool.app_id == app_id]


def _validate_app(app: AppRegistration) -> None:
    if not APP_ID_PATTERN.fullmatch(app.app_id):
        raise RegistryError(f"app_id {app.app_id!r} must match {APP_ID_PATTERN.pattern}")
    if not app.display_name.strip():
        raise RegistryError(f"app {app.app_id!r} needs a display_name")


def _validate_schema(tool_name: str, label: str, schema: Mapping[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(dict(schema))
    except SchemaError as exc:
        raise RegistryError(f"tool {tool_name!r}: {label} is not a valid JSON Schema: {exc.message}") from None
    if schema.get("type") != "object":
        raise RegistryError(f"tool {tool_name!r}: {label} must have type 'object'")


def _validate_tool(tool: ToolManifest, apps: Mapping[str, AppRegistration]) -> None:
    if tool.app_id not in apps:
        raise RegistryError(f"tool {tool.name!r} references unregistered app {tool.app_id!r}")
    name_pattern = re.compile(rf"^{re.escape(tool.app_id)}_[a-z][a-z0-9]*(_[a-z0-9]+)+$")
    if not name_pattern.fullmatch(tool.name) or len(tool.name) > 64:
        raise RegistryError(f"tool name {tool.name!r} must follow '<app>_<verb>_<noun>' (max 64 chars)")
    if not tool.description.strip():
        raise RegistryError(f"tool {tool.name!r} needs a description")
    if not tool.read_only:
        raise RegistryError(f"tool {tool.name!r}: write tools are not supported by the shared server yet")
    if not tool.allowed_roles:
        raise RegistryError(f"tool {tool.name!r} must allow at least one role")
    bad_roles = sorted(role for role in tool.allowed_roles if not ROLE_PATTERN.fullmatch(role))
    if bad_roles:
        raise RegistryError(f"tool {tool.name!r} has invalid role names {bad_roles}")
    _validate_schema(tool.name, "input_schema", tool.input_schema)
    identity_args = sorted(FORBIDDEN_ARGUMENT_NAMES & set(tool.input_schema.get("properties", {})))
    if identity_args:
        raise RegistryError(f"tool {tool.name!r} must not accept identity arguments {identity_args}")
    if tool.output_schema is not None:
        _validate_schema(tool.name, "output_schema", tool.output_schema)


def build_registry(apps: Iterable[AppRegistration] = (), tools: Iterable[ToolManifest] = ()) -> Registry:
    app_map: dict[str, AppRegistration] = {}
    for app in apps:
        _validate_app(app)
        if app.app_id in app_map:
            raise RegistryError(f"duplicate app_id {app.app_id!r}")
        app_map[app.app_id] = app

    tool_map: dict[str, ToolManifest] = {}
    for tool in tools:
        _validate_tool(tool, app_map)
        if tool.name in tool_map:
            raise RegistryError(f"duplicate tool name {tool.name!r}")
        tool_map[tool.name] = tool

    return Registry(apps=MappingProxyType(app_map), tools=MappingProxyType(tool_map))
