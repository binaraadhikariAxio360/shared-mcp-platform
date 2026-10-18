"""ASGI application: MCP Streamable HTTP endpoint plus /healthz and /readyz.

Built on the official SDK (`mcp.server.mcpserver.MCPServer`). The MCP endpoint runs stateless with
JSON responses. `ProtocolVersionGuard` pins the protocol: the initialize handshake must request the
configured version, and every other request must carry it in `MCP-Protocol-Version`. That also
blocks the SDK's stateless 2026-07-28 era, which is selected by that header.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import SERVER_NAME, __version__
from .audit import audit_event
from .config import Settings
from .registry import Registry, build_registry

PROTOCOL_VERSION_HEADER = b"mcp-protocol-version"
INVALID_REQUEST = -32600
INVALID_PARAMS = -32602


@dataclass
class ServerState:
    settings: Settings
    registry: Registry
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


def build_mcp_server() -> MCPServer:
    # No tools are registered in Step 2: tools/list returns an empty list.
    return MCPServer(name=SERVER_NAME, version=__version__)


def build_app(settings: Settings, registry: Registry | None = None) -> Starlette:
    state = ServerState(settings=settings, registry=registry if registry is not None else build_registry())
    mcp_server = build_mcp_server()
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
            Mount("", app=ProtocolVersionGuard(mcp_app, settings)),
        ],
        lifespan=lifespan,
    )
    app.state.server_state = state
    return app
