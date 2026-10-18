# Shared MCP Server — Architecture Audit & Phase 1 Plan (PractiCare)

Status: **PLAN — awaiting review/approval. Nothing below is implemented.**
Date: 2026-10-18. Scope: PractiCare agent + PractiCare MCP client + Shared MCP Server + 3 read-only PractiCare tools.
Out of scope: TaxSnap / PropSights / OnScribe agents and clients (designed for, not built), any write tool, any DB schema change.

---

## 1. Actual current PractiCare architecture (verified in code)

All paths relative to `apps/practicare/backend/`.

### 1.1 Request → agent → tool execution

| Step | Where | What actually happens |
| :--- | :--- | :--- |
| 1 | `main.py:94 get_request_context` | Bearer `pcsess.*` token verified (`security.py:77 verify_access_token`, HMAC-SHA256, key `SESSION_SECRET_KEY`). User re-loaded from DB; tenant must match token; inactive/unapproved → 401/403. Role normalized (`ai/context.py normalize_role`). |
| 2 | `main.py:2425 ai_chat_endpoint` (`POST /api/v1/ai/chat`) | Conversation ownership enforced (tenant + user). `main.py:119 build_ai_security_context` → frozen `SecurityContext` (`ai/context.py`) with role permissions from `ROLE_PERMISSIONS`. |
| 3 | `ai/agent.py:2722 PractiCareLangGraphAgent.run` | Runs the compiled `StateGraph` (`ai/agent.py:2675 _build_graph`): `agent_reasoning → tool_execution → result_analysis → (loop) → report_synthesis`. `SecurityContext` and DB session travel in the LangGraph config, never in model-visible state. |
| 4 | `ai/agent.py:848 agent_reasoning_node` | Gemini (`get_gemini_llm`, `langchain_google_genai`) bound to `registry.get_schemas_for_role(role)` (`ai/registry.py:101`) — least-privilege tool exposure; read-only questions additionally drop inventory write tools. Deterministic mode uses `_plan_tools_deterministic`. |
| 5 | `ai/agent.py:1261 tool_execution_node` | Hard guards (read-only question → no inventory writes; no implicit item creation), then **every** call goes through `gateway.execute(...)`. |
| 6 | `ai/gateway.py:84 ToolGateway.execute` | Registry lookup → tenant injection / identity-field stripping → object-level policy (`ai/policy.py`) → `allowed_roles` + `required_permissions` → Pydantic arg validation → approval interception (`ai/approvals.py`, `prepare_approval` hooks) → handler in the request DB session → rollback on failure → audit row in `ai_audit_events` (`_record_audit`, args redacted for password/token/secret/code keys). |
| 7 | `ai/handlers/*.py` | Domain handlers, tenant-scoped queries. Inventory rules come from `inventory_service.py`; task visibility from `ai/policy.py filter_visible_tasks`. |
| 8 | `ai/agent.py report_synthesis_node` → `_enforce_mutation_grounding` / `_enforce_inventory_facts` | Replies are grounded against tool evidence (no unverified IDs, no false success, no contradicting inventory claims). |
| 9 | `main.py:2584 ai_approve_endpoint` | Approval tokens (`appr-*`, argument hash, single use, tenant/user bound) executed through `gateway.execute(..., approval_id=...)`. |

### 1.2 Relevant existing components

- **Tool registry** `ai/registry.py` — 28 local tools (`ToolMetadata`, `ai/metadata.py`): names like `get_inventory_status`, `list_tasks`. No provider abstraction; handler is a Python callable.
- **Read handlers to reuse**: `ai/handlers/inventory.py execute_get_inventory_status` (stock/expiry statuses, search, filters), `ai/handlers/tasks.py execute_list_tasks` (visibility via `filter_visible_tasks`).
- **REST equivalents**: `main.py:1284 list_inventory` (`GET /api/v1/inventory`), `main.py:893 list_tasks` (`GET /api/v1/tasks`).
- **Legacy internal tool endpoints** `main.py:2094+` `POST /internal/tools/practicare.list_tasks | get_low_stock | get_practice_summary` — older contracts; `get_low_stock` does **not** use `inventory_service` (no expiry state, different semantics). **Not reused** for MCP (see §4).
- **Audit**: only `ai_audit_events` (PractiCare DB). Manual REST inventory writes are audited as `rest:inventory.*`.
- **Docker**: one compose project `shared-mcp-moc`, default bridge network `shared-mcp-moc_default`; service names resolve (`practicare-backend:8000`, `postgres-db:5432`). Backend runs `uvicorn main:app` without `--reload`, code bind-mounted; dependencies baked into image (`requirements.txt`).
- **Scaffolding**: `platform/{shared-mcp-server,tool-registry,ai-tool-gateway,auth,audit}` and `packages/{mcp-client,common-schemas,testing}` exist but are **empty** (0 files).

### 1.3 Findings that affect the design

1. **Secrets hygiene (pre-existing)**: `SESSION_SECRET_KEY` is hard-coded in `docker-compose.yml`; there is no `.gitignore`, so `apps/practicare/backend/.env` (contains the Gemini key) would be committed if `apps/` is ever added (repo has a GitHub remote). MCP secrets must not repeat this — see §6.7.
2. **Sync agent, async SDK**: the LangGraph agent and gateway are synchronous (FastAPI threadpool). The MCP SDK is async → the client wrapper runs each call with `anyio.run(...)` in the calling worker thread (no running loop there).
3. **Callback topology**: backend → MCP server → backend internal API. Backend endpoints are sync (threadpool, default 40 threads), so the callback is served concurrently; strict timeouts prevent pile-ups.
4. **Inventory grounding is name-keyed**: `_enforce_inventory_facts` and deterministic planning look for `get_inventory_status`; they must also recognise the MCP tool names.
5. **Source drift**: `apps/practicare/frontend/next.config.ts` was changed directly in the MOC (PROJECT_STATUS §000) and now differs from the isolated test copy — sync the test copy before the next bundle.

---

## 2. Proposed PractiCare + Shared MCP architecture

```
Browser ──► PractiCare backend (FastAPI)
              main.py /api/v1/ai/chat  (user session verified, SecurityContext built)
              │
              ▼
            LangGraph agent (Gemini)          tools exposed = local tools ∪ MCP tools, filtered by role
              │
              ▼
            ToolGateway.execute               ◄── single place for RBAC, validation, approvals, audit
              │
      ┌───────┴──────────────────────┐
      ▼                              ▼
  Local provider                 MCP provider (ai/mcp_client/)
  (existing handlers)            │  signs short-lived user assertion (EdDSA)
      │                          │  Streamable HTTP + service token
      ▼                          ▼
  PractiCare DB             shared-mcp-server (new container, NO DB access)
                              auth (service token → app) → assertion verify → per-tool role check
                              → app adapter (adapters/practicare) → audit log (stdout JSON)
                                 │ HTTP + adapter service token + forwarded assertion
                                 ▼
                           PractiCare backend  /internal/mcp/v1/tools/{tool}   (new)
                              re-verifies assertion (own key), replay check, reloads user from DB,
                              builds SecurityContext from DB → ToolGateway.execute(existing read tool)
                                 │
                                 ▼
                           existing handlers → PractiCare PostgreSQL
```

Principles: PractiCare stays the **only** authority for identity, tenant and data; the shared server authenticates callers, enforces the app/tool catalog and coarse role allowlist, routes, times out and logs — no business logic, no DB.

---

## 3. Component responsibilities

| Component | Responsibility | Must NOT |
| :--- | :--- | :--- |
| LangGraph agent (`ai/agent.py`) | Plan/call tools by name; synthesize; grounding guards (extended to MCP tool names) | Know whether a tool is local or remote |
| ToolGateway (`ai/gateway.py`) | RBAC, schema validation, approvals, audit for **both** providers; creates correlation ID | Trust model-supplied identity fields |
| MCP provider (`ai/mcp_client/`) | Static local contracts for MCP tools, catalog verification, assertion signing, MCP call, result mapping, timeouts, error normalization | Fall back to a local tool on any MCP error |
| Shared MCP server | Client auth, app registry, tool discovery (least privilege), assertion verification, per-tool role allowlist, adapter dispatch, timeouts, structured audit logs, health | Access any database; contain app business rules |
| PractiCare adapter (server side) | Map MCP tool → PractiCare internal endpoint, forward assertion + correlation ID, map HTTP errors | Make authorization decisions beyond the manifest |
| PractiCare internal MCP API (new, backend) | Verify adapter token + assertion, replay protection, resolve user/tenant from DB, execute existing read tool via ToolGateway | Accept identity from request body |

---

## 4. Exact integration points (planned files)

PractiCare backend (`apps/practicare/backend/`):

| File | Change |
| :--- | :--- |
| `ai/mcp_client/__init__.py` | Package |
| `ai/mcp_client/contracts.py` | Static Pydantic input/output models + `allowed_roles` for the 3 tools (local source of truth for exposure and validation) |
| `ai/mcp_client/assertion.py` | Sign/verify user assertions (Ed25519 via `pyjwt[crypto]`); in-memory `jti` replay cache |
| `ai/mcp_client/client.py` | `McpToolClient.call(tool, args, context, correlation_id)` and `list_tools()` using `mcp.Client` + `streamable_http_client`; pinned protocol; timeouts |
| `ai/mcp_client/adapter.py` | Builds `ToolMetadata` (provider=`mcp`) whose handler calls `McpToolClient`; catalog verification (name + input-schema hash) |
| `ai/registry.py` | Register MCP tools only when `PRACTICARE_MCP_TOOLS=on` and catalog verification succeeded; hide local `get_inventory_status`/`list_tasks` from **model exposure** in that mode (both stay registered for writes, deterministic mode and the internal callback) |
| `ai/metadata.py` | Optional `provider: str = "local"` attribute (default keeps current behaviour) |
| `ai/gateway.py` | Expose the per-call correlation ID to handlers (context variable); audit `tool_name` unchanged (`practicare_list_inventory` etc.) |
| `ai/agent.py` | Treat `practicare_get_inventory_status`/`practicare_list_inventory` like `get_inventory_status` in `_enforce_inventory_facts`; tool-evidence unchanged |
| `mcp_internal.py` (new router, included by `main.py`) | `POST /internal/mcp/v1/tools/{tool_name}`: adapter-token + assertion verification → DB user reload → `gateway.execute("get_inventory_status" / "list_tasks", ...)` |
| `requirements.txt` | `mcp==2.3.0` (brings `pyjwt[crypto]`, `httpx2`, `sse-starlette`, `opentelemetry-api`) → **backend image rebuild** |

Shared MCP server (new, location — see §8):
`server.py`, `config.py`, `auth/` (service tokens, assertion verification), `registry/` (app + tool manifests), `adapters/base.py`, `adapters/practicare/{inventory.py,tasks.py}`, `audit.py`, `health.py`, `tests/`, `requirements.txt`, `Dockerfile`.

No change to: other apps, DB schema, existing local tools, REST endpoints, frontend.

---

## 5. Recommended MCP SDK and transport

| Decision | Choice | Reason (verified) |
| :--- | :--- | :--- |
| SDK | **`mcp==2.3.0`** (official Python SDK, released 2026-10-02) on **both** sides | Current major line; deps satisfied by the backend image (Python 3.11.17, pydantic 2.14, starlette 1.8, anyio 4.15, uvicorn 0.54, `httpx2` 2.13 already installed). Alternative: `mcp==1.30.0` (2026-09-07, 1.x maintenance line) if you prefer the older API. |
| Protocol | **Pin `2025-11-25`** (latest *handshake* revision) | Supported by both SDK 2.3.0 (`HANDSHAKE_PROTOCOL_VERSIONS`) and 1.30.0 (`LATEST_PROTOCOL_VERSION`), so future apps on either SDK line interoperate. The newer stateless `2026-07-28` revision is only in 2.x and is ~3 months old — revisit later. Client uses `mode="legacy"`; the server rejects any other `MCP-Protocol-Version`. |
| Transport | **Streamable HTTP**, server `streamable_http_app(stateless_http=True, json_response=True)` at `/mcp` | No session affinity, no SSE needed for request/response tools, simple Docker networking, horizontal scaling later. |
| Server API | `mcp.server.mcpserver.MCPServer` (+ low-level hooks for per-request auth context) | High-level tool registration with Pydantic schemas; low-level access for filtered `tools/list`. |
| Client API | `mcp.Client(transport)` with `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=..., timeout=...))` | Custom headers carry service token + assertion; nothing identity-related in tool arguments. |

A compatibility test pins both: the client asserts the negotiated `protocol_version == "2025-11-25"`; the server test rejects `2024-11-05` and unknown versions.

---

## 6. Security and tenant isolation design

### 6.1 Two hops, two credentials
- **Hop A (PractiCare backend → MCP server)**: `Authorization: Bearer <MCP client token for app "practicare">`. Server stores only a SHA-256 hash per registered app; constant-time compare. Identifies the **calling application**.
- **Hop B (MCP server → PractiCare internal API)**: `Authorization: Bearer <adapter token>` (different secret). PractiCare accepts `/internal/mcp/*` only with it.

### 6.2 Verified user context (never from the model)
- The gateway already strips `tenant_id/user_id/user_role/permissions` from arguments; MCP tool input schemas contain no identity fields.
- Per call, the MCP provider signs a **user assertion** (JWT, EdDSA/Ed25519, `typ=mcp-user+jwt`): `iss=practicare`, `aud=shared-mcp-server`, `sub=user_id`, `tid=tenant_id`, `role` (normalized), `tool`, `cid` (correlation ID), `jti`, `iat`, `exp = iat + 60 s`. Sent as header `X-MCP-User-Assertion`, not as tool arguments.
- MCP server verifies signature with the app's **public** key from its registry, `aud`, `exp`, `iss == calling app`, `tool == requested tool`.
- PractiCare internal API **re-verifies** the same assertion with its own key, rejects reused `jti` (in-memory TTL cache — no schema change), then **reloads the user from the DB** (exists, active, approved, `user.tenant_id == tid`) and builds `SecurityContext` from the **DB role**, not the assertion. Server-side tenant resolution: the tenant is always the user's DB tenant.

### 6.3 Authorization layers (defence in depth)
1. Model exposure: only tools whose `allowed_roles` include the caller's role (existing `get_schemas_for_role`).
2. PractiCare gateway on the calling side (role + permissions + schema) — **authoritative**.
3. MCP server: app may call only its own tools; manifest role allowlist (least-privilege discovery: `tools/list` returns only tools allowed for the assertion's role).
4. PractiCare gateway again on the executing side (existing policy, `filter_visible_tasks`, tenant filters).

### 6.4 Errors and no fallback
- Normalized errors: `UNAUTHENTICATED`, `FORBIDDEN`, `VALIDATION_ERROR`, `NOT_FOUND`, `MCP_UNAVAILABLE`, `TIMEOUT`, `UPSTREAM_ERROR` → returned to LangGraph as `{"error": ..., "detail": ..., "correlation_id": ...}`.
- **Never** retry or re-route a failed MCP call to a local tool (no silent fallback, especially after FORBIDDEN). Transport retries only for connection setup (1 retry), never after the server accepted the call.

### 6.5 Audit and correlation
- One correlation ID per tool call, created in `ToolGateway.execute` (existing `aud-*` id), propagated as `cid` in the assertion and `X-Correlation-ID` header on both hops.
- PractiCare `ai_audit_events`: caller-side row (`practicare_list_inventory`, ALLOWED/BLOCKED/ERROR) **and** execution-side row (existing tool name, `input_args` include `mcp_correlation_id`) — no schema change.
- MCP server: structured JSON log per call to stdout (`ts, cid, app, tool, tenant, user, role, decision, latency_ms, error_code`); never logs tokens, assertions or full result payloads.

### 6.6 Timeouts and limits
Client: connect 3 s, call 10 s; server → backend 8 s; request body ≤ 256 KB; result size cap (e.g. 200 items, list `limit` max 200). Gemini's own budget is 60 s.

### 6.7 Secrets
- Ed25519 private key (PractiCare) and both tokens generated at deploy time into git-ignored env files (`apps/practicare/backend/.env`, `<server>/.env`), referenced via `env_file:` — **not** inline in `docker-compose.yml`.
- Add a root `.gitignore` for `.env`, `*.pem`, `practicare_fallback.db` (recommended separately; it also protects the existing Gemini key).
- Startup refuses to run with missing/short secrets; secrets never printed.

---

## 7. First three MCP tool contracts (read-only)

Names use `<app>_<verb>_<noun>`; no collision with local names. Allowed roles: `CLINIC_OWNER, INVENTORY_MANAGER, ATTENDING_PHYSICIAN, NURSE_STAFF` (Auditor excluded in phase 1 — least privilege). Executed by existing handlers, so outputs keep current field names and semantics.

### 7.1 `practicare_list_inventory`
- **Input**: `search?: str (≤100)`, `expiry_filter?: "all"|"expired"|"within_7"|"within_30"|"within_90"|"none"`, `low_stock_only?: bool`, `sort_by?: "expiry"|"stock"|"name"`, `limit?: int 1–200 (default 50)`.
- **Executes**: `get_inventory_status` with the same filters.
- **Output**: `{tenant_id, reference_date, total_catalog_items, returned_items_count, truncated, items: [{item_id, name, current_stock, unit, min_threshold, shortfall, stock_status, expiry_date, expiry_state, days_to_expiry, location, supplier, batch_number}]}`.

### 7.2 `practicare_get_inventory_status`
- **Input**: optional `item_id?: str` or `item_query?: str` (at most one).
- **Executes**: `get_inventory_status` (clinic summary, or one item).
- **Output**: `{tenant_id, reference_date, found, message, low_stock_count, out_of_stock_count, expired_count, expiring_within_30_days_count, alerts: [str], items: [...same item shape, ≤ 1 when item given]}`. Not-found keeps the exact message: *"No inventory item matching '…' was found in the current clinic inventory. No stock changes were made."*

### 7.3 `practicare_list_tasks`
- **Input**: `status?: "Pending"|"In Progress"|"Completed"`, `priority?: "Low"|"Medium"|"High"|"Critical"`, `assigned_to_me?: bool`, `overdue_only?: bool`, `limit?: int 1–50 (default 20)`.
- **Executes**: `list_tasks` (visibility via `filter_visible_tasks` — Doctors never see Owner/Manager-scope tasks, Nurses only their own).
- **Output**: `{tenant_id, total_returned, pending_count, overdue_count, tasks: [{task_id, title, status, priority, due_date, is_overdue, room_name, assigned_staff_id, assigned_to, description}]}`.

All three: `readOnlyHint=true`, `idempotentHint=true`, structured output (`outputSchema` + `structuredContent`) plus a short text summary.

---

## 8. Proposed directory structure

Your proposal places the server at repo root (`shared-mcp-server/`). The repo already has an **empty** `platform/shared-mcp-server/` documented in `CLAUDE.md` as the planned location. **Recommendation: use `platform/shared-mcp-server/`** (one home for shared platform code; leave the other empty scaffolds untouched). Either works — please choose.

```
shared-mcp-moc/
├── apps/practicare/backend/
│   ├── mcp_internal.py                 NEW  internal callback API for the adapter
│   └── ai/mcp_client/                  NEW
│       ├── __init__.py
│       ├── contracts.py                tool contracts (Pydantic in/out, roles)
│       ├── assertion.py                Ed25519 user assertions, replay cache
│       ├── client.py                   MCP Streamable HTTP client wrapper
│       └── adapter.py                  ToolMetadata provider + catalog verification
├── platform/shared-mcp-server/         NEW (or ./shared-mcp-server/)
│   ├── server.py                       MCPServer app, /mcp, /healthz, /readyz
│   ├── config.py                       env-driven settings, protocol pin
│   ├── audit.py                        structured JSON audit log
│   ├── auth/{service_tokens.py, assertions.py}
│   ├── registry/{apps.py, manifest.py} app + tool registration (data, not code paths)
│   ├── adapters/base.py                AppAdapter interface
│   ├── adapters/practicare/{__init__.py, inventory.py, tasks.py, http.py}
│   ├── tests/
│   ├── requirements.txt                mcp==2.3.0, pyjwt[crypto], uvicorn
│   ├── Dockerfile
│   └── .env.example                    variable names only
├── tests/test_mcp_practicare_*.py      NEW PractiCare-side tests
└── docker-compose.yml                  + shared-mcp-server service
```

---

## 9. Docker integration plan

```yaml
  shared-mcp-server:
    build: { context: ./platform/shared-mcp-server, dockerfile: Dockerfile }
    container_name: moc-shared-mcp-server
    env_file: ./platform/shared-mcp-server/.env     # tokens hash, public keys, adapter token
    environment:
      - MCP_PROTOCOL_VERSION=2025-11-25
      - PRACTICARE_BACKEND_URL=http://practicare-backend:8000
    expose: ["8100"]                                  # no host port by default
    healthcheck: { test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://localhost:8100/healthz')"], interval: 10s }
```
PractiCare backend gains `MCP_SERVER_URL=http://shared-mcp-server:8100/mcp`, `PRACTICARE_MCP_TOOLS=off` (feature flag) and secrets via `env_file`. Same default network — no new network needed. The server has no DB credentials and is not on any DB-only network.

Rollout (each step needs approval at deploy time): build & start only `shared-mcp-server` (`docker compose up -d --no-deps --build shared-mcp-server`) → rebuild/restart `practicare-backend` with the `mcp` dependency and flag **off** (behaviour unchanged) → turn flag **on** → restart backend. UI unchanged. Rollback: flag off + restart backend; remove the service.

---

## 10. Step-by-step implementation plan (after approval)

All in the isolated test copy first; nothing touches the running MOC until a separately approved deployment.

1. Sync test copy with MOC (`next.config.ts` drift), baseline commit.
2. Server skeleton: config (protocol pin, secrets validation), health endpoints, app/tool registry, audit logger, `AppAdapter` interface — unit tests.
3. Auth: service-token middleware, assertion verification, per-tool role allowlist, filtered `tools/list` — tests incl. wrong app, expired, wrong audience, replayed `jti`, tool mismatch.
4. PractiCare internal API (`mcp_internal.py`): adapter token + assertion verify, DB user reload, gateway execution of `get_inventory_status` / `list_tasks` — tests for every role, inactive user, tenant mismatch, forged role.
5. PractiCare adapter on the server: HTTP client, error/timeout mapping, output validation against contracts.
6. PractiCare MCP client: contracts, assertion signing, `McpToolClient`, catalog verification, `ToolMetadata` provider, feature flag, gateway correlation-ID context, agent grounding extension.
7. In-process end-to-end tests (MCP `Client` against `MCPServer` instance; adapter routed to the backend `TestClient`) — no network.
8. Docker integration test on an isolated `--internal` network with a throwaway Postgres restore.
9. Full regression suite (182 existing + new), TypeScript check (unchanged frontend), deployment bundle + rollback plan → **approval** → deploy.

Estimated new tests: ~45–60.

---

## 11. Test plan

**Automated**
- Protocol: negotiated version pinned; unsupported versions rejected; client/server SDK both 2.3.0.
- Auth: missing/invalid service token → 401; assertion missing/expired/wrong aud/wrong iss/bad signature/replayed → 401; app calling another app's tool → 403.
- Discovery: `tools/list` per role (Doctor/Nurse see the 3 read tools; unknown role sees none); catalog-hash mismatch disables MCP tools on the PractiCare side.
- Tenant isolation: assertion for tenant A cannot read tenant B; forged `tenant_id`/`role` in arguments ignored; DB role wins over assertion role.
- Behaviour parity: MCP results equal local `get_inventory_status` / `list_tasks` results for all four roles on the same fixture (incl. Doctor task visibility, Nurse own tasks, not-found message, stock/expiry statuses).
- No fallback: MCP FORBIDDEN/timeout/unavailable returns an error and executes no local tool.
- Audit: caller- and execution-side `ai_audit_events` rows share the correlation ID; server log lines contain no secrets.
- Flag off: existing 182 tests unchanged; tool exposure identical to today.

**Manual (after deployment)**
- `/healthz`, `/readyz`; backend chat as Owner, Manager, Doctor, Nurse: "Which items are expiring within 7 days?", "How many Nitrile Gloves are available?", "Show my pending tasks" — answers match the Inventory/Tasks pages; audit log shows `practicare_*` rows with correlation IDs; stop the MCP container → chat reports the tool as unavailable (no fabricated answer, no silent local fallback); write requests still work through local tools.

---

## 12. Future TaxSnap / PropSights / OnScribe onboarding (design only)

Adding an application requires **no change to the server core or the PractiCare integration**:
1. **Register** the app in `registry/apps.py` (data): `app_id`, client-token hash, assertion public key, adapter module, backend base URL, adapter token.
2. **Manifest** its tools (`<app>_<verb>_<noun>`, input/output schemas, role allowlist, read-only flag).
3. **Adapter** `adapters/<app>/` implementing `AppAdapter.call(tool, args, assertion, cid)` against that app's own internal API.
4. **App side**: the app's own agent + MCP client (same pattern as `ai/mcp_client/`), its own internal callback API doing its own identity/tenant resolution.
Isolation: service token ⇒ app; an app can only discover and call its own tools (cross-app calls require an explicit future policy); per-app keys and tokens; per-app audit fields.

---

## Decisions needed before implementation
1. Server location: `platform/shared-mcp-server/` (recommended) or root `shared-mcp-server/`.
2. SDK line: `mcp==2.3.0` (recommended) or `mcp==1.30.0`.
3. Phase 1 exposure when the flag is on: MCP read tools **replace** the local `get_inventory_status` / `list_tasks` in model exposure (recommended, avoids duplicate capabilities), or both exposed.
4. Clinical Auditor: excluded from MCP tools in phase 1 (recommended) or included with the existing anonymized task output.
5. Whether to add the root `.gitignore` and move `SESSION_SECRET_KEY` out of `docker-compose.yml` as part of this work.
