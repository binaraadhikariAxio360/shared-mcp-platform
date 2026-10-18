"""Signed user assertions: one short-lived, single-use Ed25519 JWT per protected MCP operation.

The calling application signs the assertion from its own DB-backed session (never from model
output). The server verifies it but treats the claims as the caller's statement only: the
application re-verifies the forwarded assertion and reloads the user from its database, so it
remains the final authority for user, tenant and permissions. Permission claims are never read.

Verification order: size/format -> JOSE header (`alg` must be exactly EdDSA) -> issuer bound to
the authenticated app -> key by (app, kid) -> signature -> claims -> single-use `jti`.
"""

from __future__ import annotations

import binascii
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import jwt
from jwt.api_jws import PyJWS

from ..errors import McpSecurityError
from ..registry import ROLE_PATTERN, AppRegistration
from .replay import ReplayCache

ASSERTION_HEADER = "x-mcp-user-assertion"
CORRELATION_HEADER = "x-correlation-id"
ASSERTION_TYP = "mcp-user+jwt"
MAX_ASSERTION_BYTES = 4096
ACTIONS = frozenset({"tools/list", "tools/call"})

_COMPACT_JWS = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
# Opaque ids only: '@' is excluded so an email address cannot be used as an identifier.
_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_JTI = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
# Header parameters that would let the token choose its own key, or demand unknown processing.
_FORBIDDEN_HEADER_PARAMS = frozenset({"jwk", "jku", "x5u", "x5c", "crit"})
_JWS = PyJWS(algorithms=["EdDSA"])


@dataclass(frozen=True)
class VerifiedUser:
    app_id: str
    user_id: str
    tenant_id: str
    role: str
    correlation_id: str
    action: str
    tool: str | None
    jti: str
    expires_at: float
    raw: str = field(repr=False)


def _fail(reason: str) -> McpSecurityError:
    return McpSecurityError("UNAUTHENTICATED", reason)


def _numeric_date(claims: Mapping[str, Any], name: str) -> float:
    value = claims.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail("BAD_ASSERTION")
    return float(value)


def _string(claims: Mapping[str, Any], name: str, pattern: re.Pattern[str]) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise _fail("BAD_ASSERTION")
    return value


class AssertionVerifier:
    def __init__(
        self,
        apps: Iterable[AppRegistration],
        *,
        audience: str,
        max_lifetime_seconds: int,
        clock_skew_seconds: int,
        replay_cache: ReplayCache,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._keys = {app.app_id: {key.kid: key.public_key for key in app.assertion_keys} for app in apps}
        self.audience = audience
        self.max_lifetime = max_lifetime_seconds
        self.skew = clock_skew_seconds
        self.replay_cache = replay_cache
        self._clock = clock

    def verify(
        self,
        values: list[str],
        *,
        app_id: str,
        action: str,
        tool: str | None = None,
        correlation_header: list[str] | None = None,
    ) -> VerifiedUser:
        """`values`: every X-MCP-User-Assertion header value; `app_id`: the authenticated app."""
        if action not in ACTIONS:
            raise ValueError(f"unsupported action {action!r}")
        if not values or not values[0]:
            raise _fail("MISSING_ASSERTION")
        if len(values) != 1:
            raise _fail("BAD_ASSERTION")
        token = values[0]
        if len(token) > MAX_ASSERTION_BYTES or not _COMPACT_JWS.fullmatch(token):
            raise _fail("BAD_ASSERTION")

        header = self._header(token)
        unverified = self._unverified_claims(token)
        if unverified.get("iss") != app_id:
            # The assertion must come from the same app that authenticated the request.
            raise _fail("ISSUER_APP_MISMATCH" if isinstance(unverified.get("iss"), str) else "WRONG_ISSUER")
        key = self._keys.get(app_id, {}).get(header["kid"])
        if key is None:
            raise _fail("UNKNOWN_KEY")
        try:
            payload = _JWS.decode_complete(token, key=key, algorithms=["EdDSA"])["payload"]
        except jwt.InvalidSignatureError:
            raise _fail("BAD_SIGNATURE") from None
        except jwt.PyJWTError:
            raise _fail("BAD_ASSERTION") from None
        claims = self._json_object(payload)
        return self._check_claims(claims, token, app_id, action, tool, correlation_header)

    @staticmethod
    def _header(token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise _fail("BAD_ASSERTION") from None
        if header.get("alg") != "EdDSA":  # rejects none / HS* / RS* (no algorithm confusion)
            raise _fail("BAD_ALGORITHM")
        if header.get("typ") != ASSERTION_TYP or not isinstance(header.get("kid"), str):
            raise _fail("BAD_ASSERTION")
        if _FORBIDDEN_HEADER_PARAMS & set(header):
            raise _fail("BAD_ASSERTION")
        return header

    @staticmethod
    def _json_object(payload: bytes) -> dict[str, Any]:
        try:
            claims = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            raise _fail("BAD_ASSERTION") from None
        if not isinstance(claims, dict):
            raise _fail("BAD_ASSERTION")
        return claims

    def _unverified_claims(self, token: str) -> dict[str, Any]:
        # Used only to bind the issuer to the authenticated app before choosing a key;
        # never logged and never trusted for anything else.
        segment = token.split(".")[1]
        try:
            payload = jwt.utils.base64url_decode(segment.encode("ascii"))
        except (binascii.Error, ValueError):
            raise _fail("BAD_ASSERTION") from None
        return self._json_object(payload)

    def _check_claims(
        self,
        claims: dict[str, Any],
        token: str,
        app_id: str,
        action: str,
        tool: str | None,
        correlation_header: list[str] | None,
    ) -> VerifiedUser:
        if claims.get("iss") != app_id:
            raise _fail("ISSUER_APP_MISMATCH")
        if claims.get("aud") != self.audience:  # a single string; arrays are not accepted
            raise _fail("WRONG_AUDIENCE")

        user_id = _string(claims, "sub", _SUBJECT)
        tenant_id = _string(claims, "tid", _SUBJECT)
        role = _string(claims, "role", ROLE_PATTERN)
        correlation_id = _string(claims, "cid", _CORRELATION_ID)
        jti = _string(claims, "jti", _JTI)

        act = claims.get("act")
        if act not in ACTIONS:
            raise _fail("BAD_ASSERTION")
        if act != action:
            raise _fail("ACTION_MISMATCH")
        claimed_tool = claims.get("tool")
        if action == "tools/call":
            if not isinstance(claimed_tool, str) or not _TOOL_NAME.fullmatch(claimed_tool):
                raise _fail("BAD_ASSERTION")
            if claimed_tool != tool:
                raise _fail("TOOL_MISMATCH")
        elif claimed_tool is not None:
            raise _fail("BAD_ASSERTION")

        if correlation_header:
            if len(correlation_header) != 1 or correlation_header[0] != correlation_id:
                raise _fail("CORRELATION_MISMATCH")

        issued_at = _numeric_date(claims, "iat")
        expires_at = _numeric_date(claims, "exp")
        not_before = _numeric_date(claims, "nbf") if "nbf" in claims else None
        if expires_at <= issued_at:
            raise _fail("BAD_ASSERTION")
        if expires_at - issued_at > self.max_lifetime:
            raise _fail("LIFETIME_TOO_LONG")
        now = self._clock()
        if issued_at > now + self.skew:
            raise _fail("IAT_IN_FUTURE")
        if now >= expires_at + self.skew:
            raise _fail("EXPIRED_ASSERTION")
        if not_before is not None and now + self.skew < not_before:
            raise _fail("ASSERTION_NOT_YET_VALID")

        # Only a fully verified assertion consumes its jti.
        if not self.replay_cache.consume(app_id, jti, expires_at + self.skew):
            raise _fail("REPLAYED")

        return VerifiedUser(
            app_id=app_id,
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            correlation_id=correlation_id,
            action=action,
            tool=claimed_tool if action == "tools/call" else None,
            jti=jti,
            expires_at=expires_at,
            raw=token,
        )
