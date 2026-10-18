"""ASGI application: MCP Streamable HTTP endpoint plus /healthz and /readyz.

Built on the official SDK's stable low-level API (`mcp.server.lowlevel.Server`), whose handlers
receive the HTTP request. The MCP endpoint runs stateless with JSON responses.

Request pipeline for everything under the MCP mount:
  ServiceAuthMiddleware   every request: the calling app's service token (401 otherwise)
  ProtocolVersionGuard    protocol pin (400) and body limit (413)
  SDK Streamable HTTP     DNS-rebinding protection, JSON-RPC
  low-level Server        initialize / notifications: service auth only
                          tools/list, tools/call: plus a single-use signed user assertion

`ProtocolVersionGuard` pins the protocol: the initialize handshake must request the configured
version, and every other request must carry it in `MCP-Protocol-Version`. That also blocks the
SDK's stateless 2026-07-28 era, which is selected by that header.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import mcp_types as types
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import MCPError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import SERVER_NAME, __version__
from .adapters.base import AdapterError, AppAdapter, CallContext
from .audit import arg_keys, audit_event
from .auth.assertions import ASSERTION_HEADER, CORRELATION_HEADER, AssertionVerifier, VerifiedUser
from .auth.replay import ReplayCache
from .auth.service_tokens import (
    SCOPE_STATE_KEY,
    AuthenticatedApp,
    ServiceAuthMiddleware,
    ServiceTokenVerifier,
    new_correlation_id,
)
from .authz import resolve_callable_tool, visible_tools
from .config import Settings
from .errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_UNAUTHENTICATED,
    McpSecurityError,
)
from .registry import Registry, RegistryError, ToolManifest, build_registry

PROTOCOL_VERSION_HEADER = b"mcp-protocol-version"
INVALID_REQUEST = JSONRPC_INVALID_REQUEST
INVALID_PARAMS = JSONRPC_INVALID_PARAMS

# Code -> (JSON-RPC code, generic message). Bodies carry only the code and a correlation id.
_WIRE_ERRORS = {
    "UNAUTHENTICATED": (JSONRPC_UNAUTHENTICATED, "Unauthenticated"),
    "NOT_FOUND": (JSONRPC_INVALID_PARAMS, "Unknown tool"),
    "VALIDATION_ERROR": (JSONRPC_INVALID_PARAMS, "Invalid tool arguments"),
    "MCP_UNAVAILABLE": (JSONRPC_INTERNAL_ERROR, "Service temporarily unavailable"),
    "UPSTREAM_ERROR": (JSONRPC_INTERNAL_ERROR, "Internal error"),
}


@dataclass
class ServerState:
    settings: Settings
    registry: Registry
    service_tokens: ServiceTokenVerifier
    assertions: AssertionVerifier
    adapters: Mapping[str, AppAdapter]
    ready: bool = False


def _jsonrpc_error(status: int, code: int, message: str, request_id: Any = None, data: Any = None) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": error}, status_code=status)


class ProtocolVersionGuard:
    """Rejects any MCP request that does not use the pinned protocol version."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.path = settings.mcp_path
        self.version = settings.protocol_version
        self.max_body = settings.max_request_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") != self.path:
            await self.app(scope, receive, send)
            return

        header = next((v.decode("latin-1") for k, v in scope["headers"] if k == PROTOCOL_VERSION_HEADER), None)
        if scope["method"] != "POST":
            if header != self.version:
                await self._unsupported(header)(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        body = await self._read_body(receive)
        if body is None:
            await _jsonrpc_error(413, INVALID_REQUEST, "Request body too large")(scope, receive, send)
            return

        message = self._parse(body)
        if isinstance(message, dict) and message.get("method") == "initialize":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            requested = params.get("protocolVersion")
            if requested != self.version or header not in (None, self.version):
                response = _jsonrpc_error(
                    400,
                    INVALID_PARAMS,
                    "Unsupported protocol version",
                    request_id=message.get("id"),
                    data={"supported": [self.version], "requested": requested},
                )
                await response(scope, receive, send)
                return
        elif header != self.version:
            await self._unsupported(header)(scope, receive, send)
            return

        await self.app(scope, self._replay(body), send)

    def _unsupported(self, requested: str | None) -> JSONResponse:
        return _jsonrpc_error(
            400,
            INVALID_REQUEST,
            "Bad Request: missing or unsupported MCP-Protocol-Version header",
            data={"supported": [self.version], "requested": requested},
        )

    async def _read_body(self, receive: Receive) -> bytes | None:
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_body:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    @staticmethod
    def _parse(body: bytes) -> Any:
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None  # the SDK answers malformed JSON itself

    @staticmethod
    def _replay(body: bytes) -> Receive:
        sent = False

        async def receive() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        return receive


def _wire_error(code: str, correlation_id: str, **extra: Any) -> MCPError:
    jsonrpc_code, message = _WIRE_ERRORS[code]
    return MCPError(jsonrpc_code, message, {"error": code, "correlation_id": correlation_id, **extra})


def _tool_error_result(code: str, correlation_id: str) -> types.CallToolResult:
    payload = {"error": code, "correlation_id": correlation_id}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))],
        structured_content=payload,
        is_error=True,
    )


def _mcp_tool(tool: ToolManifest) -> types.Tool:
    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=dict(tool.input_schema),
        output_schema=dict(tool.output_schema) if tool.output_schema is not None else None,
        annotations=types.ToolAnnotations(read_only_hint=tool.read_only),
    )


def _caller(ctx: ServerRequestContext[Any, Any]) -> AuthenticatedApp | None:
    request = ctx.request
    if not isinstance(request, Request):
        return None
    caller = request.scope.get("state", {}).get(SCOPE_STATE_KEY)
    return caller if isinstance(caller, AuthenticatedApp) else None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


class ToolHandlers:
    """`tools/list` and `tools/call`: verify the user assertion, then authorize (deny by default).

    Identity comes only from the service token (app) and the verified assertion (user, tenant,
    role); tool arguments never supply it. The application re-verifies everything downstream.
    """

    def __init__(self, state: ServerState) -> None:
        self.state = state

    def _verify_user(self, ctx: ServerRequestContext[Any, Any], action: str, tool: str | None) -> VerifiedUser:
        caller = _caller(ctx)
        if caller is None:  # defense in depth: ServiceAuthMiddleware always sets it
            raise McpSecurityError("UNAUTHENTICATED", "NO_SERVICE_IDENTITY")
        headers = ctx.request.headers
        return self.state.assertions.verify(
            headers.getlist(ASSERTION_HEADER),
            app_id=caller.app_id,
            action=action,
            tool=tool,
            correlation_header=headers.getlist(CORRELATION_HEADER),
        )

    async def list_tools(
        self, ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        started = time.perf_counter()
        correlation_id = new_correlation_id()
        try:
            user = self._verify_user(ctx, "tools/list", None)
            correlation_id = user.correlation_id
            tools = visible_tools(self.state.registry, user.app_id, user.role)
        except McpSecurityError as exc:
            caller = _caller(ctx)
            # Claims of an unverified assertion are never logged.
            audit_event(
                "mcp.tools.list",
                correlation_id=correlation_id,
                app=caller.app_id if caller else None,
                decision="DENIED",
                reason=exc.reason,
                latency_ms=_elapsed_ms(started),
            )
            raise _wire_error(exc.code, correlation_id) from None
        except Exception as exc:
            audit_event(
                "mcp.tools.list",
                correlation_id=correlation_id,
                decision="ERROR",
                reason="UNEXPECTED_ERROR",
                error_type=type(exc).__name__,
            )
            raise _wire_error("UPSTREAM_ERROR", correlation_id) from None

        audit_event(
            "mcp.tools.list",
            correlation_id=correlation_id,
            app=user.app_id,
            tenant=user.tenant_id,
            user=user.user_id,
            role=user.role,
            decision="ALLOWED",
            returned_tools=[tool.name for tool in tools],
            latency_ms=_elapsed_ms(started),
        )
        return types.ListToolsResult(tools=[_mcp_tool(tool) for tool in tools])

    async def call_tool(
        self, ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        started = time.perf_counter()
        correlation_id = new_correlation_id()
        arguments = params.arguments or {}
        user: VerifiedUser | None = None

        def record(decision: str, reason: str | None = None, **fields: Any) -> None:
            if user is not None:
                identity = {"app": user.app_id, "tenant": user.tenant_id, "user": user.user_id, "role": user.role}
            else:
                caller = _caller(ctx)
                identity = {"app": caller.app_id if caller else None}
            audit_event(
                "mcp.tools.call",
                correlation_id=correlation_id,
                tool=params.name[:64],
                arg_keys=arg_keys(arguments),
                decision=decision,
                reason=reason,
                latency_ms=_elapsed_ms(started),
                **identity,
                **fields,
            )

        try:
            user = self._verify_user(ctx, "tools/call", params.name)
            correlation_id = user.correlation_id
            tool = resolve_callable_tool(self.state.registry, user.app_id, user.role, params.name)
            if tool is None:
                # Hidden, forbidden and nonexistent tools are indistinguishable to the caller.
                raise McpSecurityError("NOT_FOUND", "UNKNOWN_TOOL")
            error = best_match(Draft202012Validator(dict(tool.input_schema)).iter_errors(arguments))
            if error is not None:
                record("DENIED", "VALIDATION_ERROR", schema_keyword=error.validator)
                # The failing location and keyword only; argument values are never echoed.
                raise _wire_error(
                    "VALIDATION_ERROR",
                    correlation_id,
                    pointer="/" + "/".join(str(part) for part in error.absolute_path),
                    keyword=str(error.validator),
                )
        except McpSecurityError as exc:
            record("DENIED", exc.reason)
            raise _wire_error(exc.code, correlation_id) from None
        except MCPError:
            raise
        except Exception as exc:
            record("ERROR", "UNEXPECTED_ERROR", error_type=type(exc).__name__)
            raise _wire_error("UPSTREAM_ERROR", correlation_id) from None

        context = CallContext(
            correlation_id=correlation_id,
            app_id=user.app_id,
            tool_name=tool.name,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            role=user.role,
            assertion=user.raw,
        )
        try:
            result = await self.state.adapters[tool.app_id].call_tool(dict(arguments), context)
            if not isinstance(result, dict):
                raise TypeError("adapter result is not an object")
            if tool.output_schema is not None and best_match(
                Draft202012Validator(dict(tool.output_schema)).iter_errors(result)
            ):
                raise ValueError("adapter result does not match the output schema")
        except AdapterError as exc:
            record("ERROR", "ADAPTER_ERROR", error_code=exc.code)
            return _tool_error_result(exc.code, correlation_id)
        except Exception as exc:
            record("ERROR", "UPSTREAM_ERROR", error_type=type(exc).__name__)
            return _tool_error_result("UPSTREAM_ERROR", correlation_id)

        record("ALLOWED", outcome="SUCCESS")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(result, default=str))],
            structured_content=result,
        )


def build_mcp_server(state: ServerState) -> Server:
    handlers = ToolHandlers(state)
    return Server(
        SERVER_NAME,
        version=__version__,
        on_list_tools=handlers.list_tools,
        on_call_tool=handlers.call_tool,
    )


def _adapter_map(registry: Registry, adapters: Iterable[AppAdapter]) -> dict[str, AppAdapter]:
    mapping: dict[str, AppAdapter] = {}
    for adapter in adapters:
        if adapter.app_id not in registry.apps:
            raise RegistryError(f"adapter for unregistered app {adapter.app_id!r}")
        if adapter.app_id in mapping:
            raise RegistryError(f"duplicate adapter for app {adapter.app_id!r}")
        mapping[adapter.app_id] = adapter
    missing = sorted({tool.app_id for tool in registry.tools.values()} - set(mapping))
    if missing:
        raise RegistryError(f"apps {missing} have tools but no adapter")
    return mapping


def build_app(
    settings: Settings,
    registry: Registry | None = None,
    adapters: Iterable[AppAdapter] = (),
    *,
    clock: Callable[[], float] = time.time,
) -> Starlette:
    registry = registry if registry is not None else build_registry()
    state = ServerState(
        settings=settings,
        registry=registry,
        service_tokens=ServiceTokenVerifier(registry.apps.values(), clock=clock),
        assertions=AssertionVerifier(
            registry.apps.values(),
            audience=settings.assertion_audience,
            max_lifetime_seconds=settings.assertion_max_lifetime_seconds,
            clock_skew_seconds=settings.clock_skew_seconds,
            replay_cache=ReplayCache(max_entries=settings.replay_cache_max_entries, clock=clock),
            clock=clock,
        ),
        adapters=_adapter_map(registry, adapters),
    )
    mcp_server = build_mcp_server(state)
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        stateless_http=True,
        json_response=True,
        max_request_body_size=settings.max_request_body_bytes,
        host=settings.host,  # loopback host => SDK enables DNS-rebinding (Host/Origin) protection
    )

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": SERVER_NAME, "version": __version__})

    async def readyz(_: Request) -> JSONResponse:
        if not state.ready:
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse(
            {
                "status": "ready",
                "protocol_version": settings.protocol_version,
                "transport": "streamable-http",
                "registered_apps": len(state.registry.apps),
                "registered_tools": len(state.registry.tools),
            }
        )

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with mcp_server.session_manager.run():
            state.ready = True
            audit_event(
                "server.started",
                version=__version__,
                protocol_version=settings.protocol_version,
                host=settings.host,
                port=settings.port,
                registered_apps=len(state.registry.apps),
                registered_tools=len(state.registry.tools),
                replay_protection="in-memory, single worker only",
            )
            try:
                yield
            finally:
                state.ready = False
                audit_event("server.stopped", version=__version__)

    app = Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route("/readyz", readyz, methods=["GET"]),
            # Everything under the MCP mount, unknown paths included, requires a service token.
            Mount("", app=ServiceAuthMiddleware(ProtocolVersionGuard(mcp_app, settings), state.service_tokens)),
        ],
        lifespan=lifespan,
    )
    app.state.server_state = state
    return app
