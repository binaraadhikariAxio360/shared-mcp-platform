"""Application and tool registry (data only).

Applications and their tool manifests are declared as data and validated once at startup;
an invalid registry prevents the server from starting. The production registry has no tools yet.

An application registration holds only verification material: SHA-256 hashes of its service
tokens and the Ed25519 public keys of its user-assertion signer. The server holds no secrets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]{1,31}$")
ROLE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
CREDENTIAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# Identity is resolved server-side from verified credentials, never from tool arguments.
FORBIDDEN_ARGUMENT_NAMES = frozenset(
    {"tenant_id", "tenant", "user_id", "user", "user_role", "role", "roles", "permissions"}
)
# Compared after lower-casing and removing '_' and '-', so 'tenantId' or 'TENANT-ID' are caught too.
_FORBIDDEN_NORMALIZED = frozenset(
    {name.replace("_", "") for name in FORBIDDEN_ARGUMENT_NAMES}
    | {"permission", "tid", "sub", "actor", "onbehalfof", "impersonate"}
)
# Roles that may never be granted an MCP tool in phase 1 (read-only audit role).
EXCLUDED_ROLES = frozenset({"CLINICAL_AUDITOR"})


class RegistryError(ValueError):
    """Raised when an application or tool declaration is invalid."""


@dataclass(frozen=True)
class ServiceCredential:
    """A service token the app may present; only its SHA-256 hash is stored."""

    token_id: str
    sha256: str
    not_after: datetime
    not_before: datetime | None = None


@dataclass(frozen=True)
class AssertionKey:
    """An Ed25519 public key that verifies the app's signed user assertions."""

    kid: str
    public_key: Ed25519PublicKey = field(repr=False)


@dataclass(frozen=True)
class AppRegistration:
    app_id: str
    display_name: str
    client_tokens: tuple[ServiceCredential, ...] = ()
    assertion_keys: tuple[AssertionKey, ...] = ()


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
    token_ids: set[str] = set()
    for credential in app.client_tokens:
        if not CREDENTIAL_ID_PATTERN.fullmatch(credential.token_id):
            raise RegistryError(f"app {app.app_id!r}: token_id {credential.token_id!r} is invalid")
        if credential.token_id in token_ids:
            raise RegistryError(f"app {app.app_id!r}: duplicate token_id {credential.token_id!r}")
        token_ids.add(credential.token_id)
        if not SHA256_HEX_PATTERN.fullmatch(credential.sha256):
            raise RegistryError(f"app {app.app_id!r}: token {credential.token_id!r} sha256 must be 64 lowercase hex")
        if credential.not_after.tzinfo is None or (
            credential.not_before is not None and credential.not_before.tzinfo is None
        ):
            raise RegistryError(f"app {app.app_id!r}: token {credential.token_id!r} validity needs a timezone")
        if credential.not_before is not None and credential.not_before >= credential.not_after:
            raise RegistryError(f"app {app.app_id!r}: token {credential.token_id!r} not_before must precede not_after")
    kids: set[str] = set()
    for key in app.assertion_keys:
        if not CREDENTIAL_ID_PATTERN.fullmatch(key.kid):
            raise RegistryError(f"app {app.app_id!r}: kid {key.kid!r} is invalid")
        if key.kid in kids:
            raise RegistryError(f"app {app.app_id!r}: duplicate kid {key.kid!r}")
        kids.add(key.kid)
        if not isinstance(key.public_key, Ed25519PublicKey):
            raise RegistryError(f"app {app.app_id!r}: key {key.kid!r} is not an Ed25519 public key")


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
    excluded = sorted(EXCLUDED_ROLES & tool.allowed_roles)
    if excluded:
        raise RegistryError(f"tool {tool.name!r} must not allow excluded roles {excluded}")
    _validate_schema(tool.name, "input_schema", tool.input_schema)
    identity_args = sorted(
        name
        for name in tool.input_schema.get("properties", {})
        if str(name).lower().replace("_", "").replace("-", "") in _FORBIDDEN_NORMALIZED
    )
    if identity_args:
        raise RegistryError(f"tool {tool.name!r} must not accept identity arguments {identity_args}")
    if tool.input_schema.get("additionalProperties") is not False:
        raise RegistryError(f"tool {tool.name!r}: input_schema must set additionalProperties to false")
    if tool.output_schema is not None:
        _validate_schema(tool.name, "output_schema", tool.output_schema)


def build_registry(apps: Iterable[AppRegistration] = (), tools: Iterable[ToolManifest] = ()) -> Registry:
    app_map: dict[str, AppRegistration] = {}
    for app in apps:
        _validate_app(app)
        if app.app_id in app_map:
            raise RegistryError(f"duplicate app_id {app.app_id!r}")
        app_map[app.app_id] = app

    # A token hash must identify exactly one app, otherwise the caller's identity is ambiguous.
    seen_hashes: set[str] = set()
    for app in app_map.values():
        for credential in app.client_tokens:
            if credential.sha256 in seen_hashes:
                raise RegistryError(f"service token hash of {app.app_id!r}/{credential.token_id!r} is registered twice")
            seen_hashes.add(credential.sha256)

    tool_map: dict[str, ToolManifest] = {}
    for tool in tools:
        _validate_tool(tool, app_map)
        if tool.name in tool_map:
            raise RegistryError(f"duplicate tool name {tool.name!r}")
        tool_map[tool.name] = tool

    return Registry(apps=MappingProxyType(app_map), tools=MappingProxyType(tool_map))
