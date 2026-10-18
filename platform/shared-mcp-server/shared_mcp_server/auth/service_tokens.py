"""Hop A: the calling application authenticates every request with a service token.

Token format `mcpsvc_` + 43 base64url characters (32 random bytes), sent as
`Authorization: Bearer <token>`. The server stores only SHA-256 hashes, each with a validity
window. Every failure returns the same HTTP 401 body; the precise reason is audit-only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

from ..audit import audit_event
from ..errors import JSONRPC_UNAUTHENTICATED, McpSecurityError
from ..registry import AppRegistration

TOKEN_PREFIX = "mcpsvc_"
TOKEN_PATTERN = re.compile(r"^mcpsvc_[A-Za-z0-9_-]{43}$")
SCOPE_STATE_KEY = "shared_mcp.app"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_correlation_id() -> str:
    return "srv-" + secrets.token_hex(8)


@dataclass(frozen=True)
class AuthenticatedApp:
    app_id: str
    token_id: str


class ServiceTokenVerifier:
    def __init__(self, apps: Iterable[AppRegistration], clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._entries = [
            (bytes.fromhex(credential.sha256), app.app_id, credential)
            for app in apps
            for credential in app.client_tokens
        ]

    def verify(self, authorization: list[str]) -> AuthenticatedApp:
        """`authorization` holds every Authorization header value of the request."""
        if not authorization:
            raise McpSecurityError("UNAUTHENTICATED", "MISSING_TOKEN")
        if len(authorization) != 1:
            raise McpSecurityError("UNAUTHENTICATED", "INVALID_TOKEN")
        scheme, _, token = authorization[0].partition(" ")
        if scheme.lower() != "bearer" or not TOKEN_PATTERN.fullmatch(token):
            raise McpSecurityError("UNAUTHENTICATED", "INVALID_TOKEN")

        digest = hashlib.sha256(token.encode("ascii")).digest()
        match = None
        for stored, app_id, credential in self._entries:  # no early exit: constant work per request
            if hmac.compare_digest(stored, digest) and match is None:
                match = (app_id, credential)
        if match is None:
            raise McpSecurityError("UNAUTHENTICATED", "INVALID_TOKEN")

        app_id, credential = match
        now = self._clock()
        if credential.not_before is not None and now < credential.not_before.timestamp():
            raise McpSecurityError("UNAUTHENTICATED", "TOKEN_NOT_YET_VALID")
        if now >= credential.not_after.timestamp():
            raise McpSecurityError("UNAUTHENTICATED", "EXPIRED_TOKEN")
        return AuthenticatedApp(app_id=app_id, token_id=credential.token_id)


def unauthenticated_body(correlation_id: str) -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": JSONRPC_UNAUTHENTICATED,
                "message": "Unauthenticated",
                "data": {"error": "UNAUTHENTICATED", "correlation_id": correlation_id},
            },
        },
        separators=(",", ":"),
    ).encode()


class ServiceAuthMiddleware:
    """Authenticates every HTTP request that reaches the wrapped MCP application.

    On success the authenticated app is stored in `scope["state"][SCOPE_STATE_KEY]`, where the
    tool handlers read it. Nothing from the client can set that value.
    """

    def __init__(self, app: ASGIApp, verifier: ServiceTokenVerifier) -> None:
        self.app = app
        self.verifier = verifier
        self._seen_tokens: set[str] = set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        values = [v.decode("latin-1") for k, v in scope["headers"] if k == b"authorization"]
        try:
            caller = self.verifier.verify(values)
        except McpSecurityError as exc:
            correlation_id = new_correlation_id()
            audit_event(
                "mcp.auth.service",
                correlation_id=correlation_id,
                method=scope["method"],
                path=scope["path"],
                decision="DENIED",
                reason=exc.reason,
            )
            await self._reject(send, correlation_id)
            return

        if caller.token_id not in self._seen_tokens:
            self._seen_tokens.add(caller.token_id)
            audit_event("mcp.auth.service", app=caller.app_id, token_id=caller.token_id, decision="ALLOWED")
        scope.setdefault("state", {})[SCOPE_STATE_KEY] = caller
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send, correlation_id: str) -> None:
        body = unauthenticated_body(correlation_id)
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b'Bearer realm="shared-mcp-server"'),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
