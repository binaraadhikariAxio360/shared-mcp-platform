"""Test-only apps, tools, adapter and credentials.

Every key and token is generated freshly per test run in memory; nothing here is a real
credential and nothing is written to disk. The `testapp` / `otherapp` registrations and their
tools exist only inside the tests: the production registry stays empty.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shared_mcp_server.adapters.base import AdapterError, AppAdapter, CallContext
from shared_mcp_server.auth.service_tokens import hash_token
from shared_mcp_server.registry import (
    AppRegistration,
    AssertionKey,
    Registry,
    ServiceCredential,
    ToolManifest,
    build_registry,
)

PINNED = "2025-11-25"
ACCEPT = "application/json, text/event-stream"
AUDIENCE = "shared-mcp-server"
CLINICAL_ROLES = ("CLINIC_OWNER", "INVENTORY_MANAGER", "ATTENDING_PHYSICIAN", "NURSE_STAFF")
_DELETE = object()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign_eddsa(claims: dict[str, Any], header: dict[str, Any], key: Ed25519PrivateKey) -> str:
    """Compact JWS signed by hand, so tests can also produce tokens PyJWT would refuse to encode."""
    signing_input = b64url(json.dumps(header).encode()) + "." + b64url(json.dumps(claims).encode())
    return signing_input + "." + b64url(key.sign(signing_input.encode()))


def new_service_token() -> str:
    return "mcpsvc_" + secrets.token_urlsafe(32)


def new_jti() -> str:
    return secrets.token_urlsafe(24)


def new_cid() -> str:
    return "cid-" + secrets.token_hex(8)


def utc(offset: timedelta) -> datetime:
    return datetime.now(timezone.utc) + offset


@dataclass
class AppCreds:
    app_id: str
    token: str = field(default_factory=new_service_token)
    private_key: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate, repr=False)
    kid: str = field(default_factory=lambda: "kid-" + secrets.token_hex(4))

    def credential(self, **overrides: Any) -> ServiceCredential:
        values: dict[str, Any] = {
            "token_id": f"{self.app_id}-svc-1",
            "sha256": hash_token(self.token),
            "not_after": utc(timedelta(days=30)),
        }
        values.update(overrides)
        return ServiceCredential(**values)

    def registration(self, credentials: tuple[ServiceCredential, ...] | None = None) -> AppRegistration:
        return AppRegistration(
            app_id=self.app_id,
            display_name=self.app_id.title(),
            client_tokens=credentials if credentials is not None else (self.credential(),),
            assertion_keys=(AssertionKey(kid=self.kid, public_key=self.private_key.public_key()),),
        )

    def claims(self, action: str = "tools/list", tool: str | None = None, **overrides: Any) -> dict[str, Any]:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.app_id,
            "aud": AUDIENCE,
            "sub": "usr-0001",
            "tid": "tenant-001",
            "role": "NURSE_STAFF",
            "act": action,
            "cid": new_cid(),
            "jti": new_jti(),
            "iat": now,
            "exp": now + 30,
        }
        if tool is not None:
            claims["tool"] = tool
        for key, value in overrides.items():
            if value is _DELETE:
                claims.pop(key, None)
            else:
                claims[key] = value
        return claims

    def assertion(
        self,
        action: str = "tools/list",
        tool: str | None = None,
        *,
        key: Ed25519PrivateKey | None = None,
        headers: dict[str, Any] | None = None,
        **overrides: Any,
    ) -> str:
        jose = {"alg": "EdDSA", "typ": "mcp-user+jwt", "kid": self.kid}
        jose.update(headers or {})
        return sign_eddsa(self.claims(action, tool, **overrides), jose, key or self.private_key)

    def headers(self, assertion: str | None = None, **extra: str) -> dict[str, str]:
        values = {
            "Accept": ACCEPT,
            "Content-Type": "application/json",
            "MCP-Protocol-Version": PINNED,
            "Authorization": f"Bearer {self.token}",
        }
        if assertion is not None:
            values["X-MCP-User-Assertion"] = assertion
        values.update(extra)
        return values


DELETE = _DELETE

ECHO_INPUT = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "maxLength": 200},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "additionalProperties": False,
}
ECHO_OUTPUT = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "app_id": {"type": "string"},
        "user_id": {"type": "string"},
        "tenant_id": {"type": "string"},
        "role": {"type": "string"},
        "correlation_id": {"type": "string"},
        "arguments": {"type": "object"},
    },
    "required": ["tool", "app_id", "user_id", "tenant_id", "role", "correlation_id", "arguments"],
}


class EchoAdapter(AppAdapter):
    """Echoes the verified context. message 'adapter-timeout' / 'adapter-crash' simulate failures."""

    def __init__(self, app_id: str) -> None:
        self.app_id = app_id
        self.calls: list[tuple[dict[str, Any], CallContext]] = []

    async def call_tool(self, arguments: dict[str, Any], context: CallContext) -> dict[str, Any]:
        self.calls.append((dict(arguments), context))
        if arguments.get("message") == "adapter-timeout":
            raise AdapterError("TIMEOUT", "upstream did not answer; secret-detail-xyz")
        if arguments.get("message") == "adapter-crash":
            raise RuntimeError("Traceback secret-detail-xyz")
        if arguments.get("message") == "adapter-bad-output":
            return {"unexpected": True}
        return {
            "tool": context.tool_name,
            "app_id": context.app_id,
            "user_id": context.user_id,
            "tenant_id": context.tenant_id,
            "role": context.role,
            "correlation_id": context.correlation_id,
            "arguments": dict(arguments),
        }


def echo_tool(app_id: str, name: str, roles: tuple[str, ...] = CLINICAL_ROLES) -> ToolManifest:
    return ToolManifest(
        name=name,
        app_id=app_id,
        description=f"Test-only tool {name}",
        input_schema=ECHO_INPUT,
        output_schema=ECHO_OUTPUT,
        allowed_roles=frozenset(roles),
    )


@dataclass
class SecurityWorld:
    """Two registered apps with fresh credentials, their test tools and echo adapters."""

    testapp: AppCreds
    otherapp: AppCreds
    registry: Registry
    adapters: dict[str, EchoAdapter]

    @property
    def adapter_list(self) -> list[EchoAdapter]:
        return list(self.adapters.values())


def make_world(testapp_credentials: tuple[ServiceCredential, ...] | None = None, with_tools: bool = True) -> SecurityWorld:
    testapp = AppCreds("testapp")
    otherapp = AppCreds("otherapp")
    tools = (
        [
            echo_tool("testapp", "testapp_echo_context"),
            echo_tool("testapp", "testapp_get_owner_summary", ("CLINIC_OWNER",)),
            echo_tool("otherapp", "otherapp_echo_context"),
        ]
        if with_tools
        else []
    )
    registry = build_registry(
        [testapp.registration(testapp_credentials), otherapp.registration()],
        tools,
    )
    adapters = {"testapp": EchoAdapter("testapp"), "otherapp": EchoAdapter("otherapp")} if with_tools else {}
    return SecurityWorld(testapp=testapp, otherapp=otherapp, registry=registry, adapters=adapters)


def rpc(method: str, params: dict[str, Any] | None = None, request_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


def call_body(name: str, arguments: dict[str, Any] | None = None, request_id: int = 1) -> dict[str, Any]:
    return rpc("tools/call", {"name": name, "arguments": arguments or {}}, request_id)


async def post(url: str, body: Any, headers: dict[str, str]) -> httpx2.Response:
    async with httpx2.AsyncClient(timeout=10) as http:
        return await http.post(url, json=body, headers=headers)
