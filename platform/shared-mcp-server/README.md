# Shared MCP Server (Step 3 — authenticated foundation)

Shared Model Context Protocol server for the MOC applications
(designs: `docs/SHARED_MCP_ARCHITECTURE_PLAN.md`, `docs/SHARED_MCP_STEP3_SECURITY_DESIGN.md`).

**Included**: a real MCP server on the official Python SDK with Streamable HTTP, `/healthz`,
`/readyz`, configuration, a validated app/tool registry (no production tools), a redacting audit
logger, the adapter interface, and **Step 3 security**: service-token authentication of the
calling app, signed single-use user assertions, replay protection and deny-by-default tool
authorization. **Not included**: application tools, the PractiCare MCP client, LangGraph
integration, Docker. The server still refuses to bind to anything but loopback. Do not deploy it.

## Verified stack

| Item | Value |
| :--- | :--- |
| SDK | `mcp==2.3.0` (official, low-level `mcp.server.lowlevel.Server`) |
| Python | 3.12.10 (local venv) |
| Transport | Streamable HTTP at `/mcp`, stateless, JSON responses |
| Protocol | pinned to `2025-11-25` (newest initialize-handshake revision in SDK 2.3.0) |
| Crypto | `PyJWT==2.15.1` (EdDSA), `cryptography==50.0.2` |

Protocol pinning (`ProtocolVersionGuard` in `server.py`): `initialize` must request the pinned
version; every other request must send `MCP-Protocol-Version: <pinned>`. Anything else gets
HTTP 400 with a JSON-RPC error listing the supported version. This also disables the SDK's
stateless `2026-07-28` era. Bodies over `MCP_MAX_REQUEST_BODY_BYTES` get HTTP 413. The SDK's
DNS-rebinding protection (Host/Origin allowlist for loopback) stays active.

## Security model (Step 3)

```
HTTP request
 └─ ServiceAuthMiddleware   every request under the MCP mount     401 if token missing/invalid/expired
     └─ ProtocolVersionGuard                                       400 / 413
         └─ SDK Streamable HTTP (DNS-rebinding protection)
             └─ low-level Server
                 ├─ initialize, notifications, ping              service token only
                 ├─ tools/list  → verify assertion (act=tools/list) → consume jti → visible tools
                 └─ tools/call  → verify assertion (act=tools/call, tool=name) → consume jti
                                  → visible? else NOT_FOUND → JSON Schema → adapter(verified context)
```

- **Service token (app → server)**: `Authorization: Bearer mcpsvc_<43 base64url>`. The server
  stores only SHA-256 hashes, each with a mandatory `not_after` (≤ 180 days) and optional
  `not_before`; several tokens per app allow rotation. Every failure gets the same 401 body.
- **User assertion (per protected operation)**: `X-MCP-User-Assertion: <JWT>`, `alg=EdDSA`
  only, `typ=mcp-user+jwt`, `kid`. Claims: `iss` (= the authenticated app), `aud`, `sub`, `tid`,
  `role` (canonical), `act` (`tools/list`|`tools/call`), `tool` (for calls), `cid`, `jti`,
  `iat`, `exp` (lifetime ≤ 60 s, skew ≤ 5 s), optional `nbf`. Permission claims are ignored.
  The client must create **a fresh assertion for every `tools/list` and `tools/call` HTTP
  request**: the SDK client's `call_tool` also sends a hidden `tools/list` (see C11 in the
  design doc and `PerRequestAssertionAuth` in `tests/test_mcp_protocol.py`).
- **Identity never comes from tool arguments**: input schemas must set
  `additionalProperties: false` and may not declare identity properties; tenant/role headers are
  ignored; the adapter gets user, tenant and role only from the verified assertion.
- **Deny by default**: no anonymous discovery; a tool is visible only to its own app and its
  allowlisted roles; `CLINICAL_AUDITOR` can never be granted a tool (startup error); hidden,
  forbidden and unknown tools all return the same `NOT_FOUND`.
- **Final authority stays in the application**: the adapter forwards the raw assertion; the
  application (PractiCare, Step 4) re-verifies it, reloads the user from its database and applies
  its own roles, permissions, object policy and tenant checks.
- **Errors**: JSON-RPC errors carry only `data.error` and `data.correlation_id`; adapter failures
  become `isError` results with the same two fields. No stack traces, tokens or argument values.
- **Audit**: one JSON line per decision (`mcp.auth.service`, `mcp.tools.list`, `mcp.tools.call`)
  with opaque ids, decision and reason; argument names only; claims of unverified assertions are
  never logged; tokens, JWTs and emails are redacted.

### Replay protection: single worker only

The replay cache (`auth/replay.py`) is **in process memory**. It is correct only for one server
process (`workers=1`, one replica), which `__main__.py` enforces. **Before any multi-worker or
multi-replica deployment, a shared replay store is required** (for example Redis
`SET <iss>:<jti> 1 NX EX <ttl>`); otherwise an assertion could be replayed once per process.
When the cache is full of unexpired entries the server fails closed (`MCP_UNAVAILABLE`).

### Credentials

`MCP_APPS_FILE` points to a JSON file with each app's token hashes and Ed25519 **public** keys
(structure: `config/apps.example.json`, placeholders only). It holds no secrets, but keep the
real file under `secrets/` (git-ignored). Startup refuses invalid files (unknown fields, bad or
duplicate hashes/kids, expired or > 180-day tokens, non-Ed25519 keys, any private key material).
Unset → zero apps → every `/mcp` request is 401. The service tokens and assertion private keys
live only in the calling application's secret store (generation tooling: Step 8).

## Layout

```
shared_mcp_server/
  config.py             env settings (loopback-only host, protocol pin, limits, auth settings)
  server.py             ASGI app: /mcp, /healthz, /readyz, protocol guard, tool handlers
  auth/service_tokens.py  service-token verifier + ASGI middleware (401)
  auth/assertions.py    Ed25519 user-assertion verifier
  auth/replay.py        single-use jti cache (single worker only)
  authz.py              visible_tools / resolve_callable_tool (deny by default)
  apps_config.py        MCP_APPS_FILE loader and validation
  registry.py           app + tool manifests (data) and validation
  errors.py             error codes, McpSecurityError
  audit.py              one-line JSON audit events with redaction
  adapters/base.py      AppAdapter interface, CallContext (verified identity)
  __main__.py           `python -m shared_mcp_server` (single worker)
config/apps.example.json  registration file structure (placeholders)
tests/                  unittest suite (real uvicorn on 127.0.0.1, ephemeral port;
                        test-only apps/tools and per-run ephemeral keys)
```

## Local use (PowerShell, from this directory)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python -m shared_mcp_server          # http://127.0.0.1:8100 (no apps => all /mcp 401)
```

Settings: see `.env.example` (environment variables; no secrets).
