# Shared MCP Server (Step 2 — foundation)

Foundation of the shared Model Context Protocol server for the MOC applications
(design: `docs/SHARED_MCP_ARCHITECTURE_PLAN.md`).

**Step 2 scope**: a real MCP server on the official Python SDK with Streamable HTTP, `/healthz`,
`/readyz`, configuration, a validated (empty) app/tool registry, a redacting audit logger and the
adapter interface. **Not included**: application tools, authentication, the PractiCare MCP client,
LangGraph integration, Docker. The endpoint is unauthenticated, so the server refuses to bind to
anything but loopback. Do not expose or deploy it.

## Verified stack

| Item | Value |
| :--- | :--- |
| SDK | `mcp==2.3.0` (official, `mcp.server.mcpserver.MCPServer`) |
| Python | 3.12.10 (local venv) |
| Transport | Streamable HTTP at `/mcp`, stateless, JSON responses |
| Protocol | pinned to `2025-11-25` (newest initialize-handshake revision in SDK 2.3.0) |

Protocol pinning (`ProtocolVersionGuard` in `server.py`): `initialize` must request the pinned
version; every other request must send `MCP-Protocol-Version: <pinned>`. Anything else gets
HTTP 400 with a JSON-RPC error listing the supported version. This also disables the SDK's
stateless `2026-07-28` era. Bodies over `MCP_MAX_REQUEST_BODY_BYTES` get HTTP 413. The SDK's
DNS-rebinding protection (Host/Origin allowlist for loopback) stays active.

## Layout

```
shared_mcp_server/
  config.py          env settings (loopback-only host, protocol pin, limits)
  server.py          ASGI app: /mcp, /healthz, /readyz, protocol guard
  registry.py        app + tool manifests (data) and validation
  audit.py           one-line JSON audit events with redaction
  adapters/base.py   AppAdapter interface, normalized error codes
  __main__.py        `python -m shared_mcp_server`
tests/               unittest suite (real uvicorn on 127.0.0.1, ephemeral port)
```

## Local use (PowerShell, from this directory)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python -m shared_mcp_server          # http://127.0.0.1:8100
```

Settings: see `.env.example` (environment variables; no secrets in Step 2).
