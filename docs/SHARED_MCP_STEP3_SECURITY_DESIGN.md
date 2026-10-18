# Shared MCP — Step 3 Security Design (Authentication & Authorization)

Status: **APPROVED (7 decisions, 2026-10-18) and IMPLEMENTED in `platform/shared-mcp-server/` — not committed, not deployed.** See §10 for the implementation record.
Date: 2026-10-18. Base: `feature/shared-mcp-step2` @ `8b474fc` (clean tree verified).
Scope: `platform/shared-mcp-server/` only. No PractiCare backend, client, tools, LangGraph, Docker or DB changes.

---

## 1. Verified starting point

| Item | Verified state |
| :--- | :--- |
| Step 2 server | `MCPServer` (high-level API), Streamable HTTP `/mcp` stateless + JSON, `ProtocolVersionGuard` pin `2025-11-25`, `/healthz`, `/readyz`, loopback-only config, empty validated registry, redacting audit log, `AppAdapter` ABC. 43 tests. |
| Crypto libs in server venv | `PyJWT 2.15.1` + `cryptography 50.0.2` (already pulled in by `mcp 2.3.0`); EdDSA (Ed25519) supported. |
| SDK hook for per-request auth | **Probed** (throwaway script, real HTTP): low-level `mcp.server.lowlevel.Server` handlers `on_list_tools(ctx, params)` / `on_call_tool(ctx, params)` receive `ctx.request` = Starlette `Request`; its headers and `scope["state"]` written by an outer ASGI middleware are visible in both handlers. |
| PractiCare backend image | No `pyjwt`/`mcp` installed → the signer (Step 6) needs an image rebuild later (already in the plan). Not touched now. |

## 2. PractiCare security review (what MCP must preserve)

All paths in `apps/practicare/backend/`.

| Area | Finding | Consequence for MCP |
| :--- | :--- | :--- |
| Session auth `security.py` | `pcsess.<payload>.<sig>` HMAC-SHA256, 7-day lifetime, constant-time compare; `iss` not checked; key from `SESSION_SECRET_KEY` (≥32 chars). | The browser session token never leaves PractiCare; MCP uses separate credentials (no reuse, no rotation of existing secrets). |
| Request identity `main.py:94 get_request_context` | User **reloaded from DB**; token `tenant_id` must equal DB tenant; inactive/unapproved rejected; role taken from **DB** and normalized. | Same rule at the final authority (Step 4 internal API): assertion claims are hints, DB is truth. |
| `ai/context.py SecurityContext.create` | Role normalized via `ROLE_ALIASES`; unknown roles rejected; permissions = static `ROLE_PERMISSIONS[role]`. | Assertions carry the **canonical** role (`CLINIC_OWNER`, `INVENTORY_MANAGER`, `ATTENDING_PHYSICIAN`, `NURSE_STAFF`, `CLINICAL_AUDITOR`). Aliases are not accepted by the server. |
| `ai/gateway.py ToolGateway.execute` | Forces `tenant_id = context.tenant_id`; strips `user_id`, `user_role`, `permissions` from arguments; `allowed_roles` + `required_permissions`; object-level policy (`ai/policy.py`); approvals; audit to `ai_audit_events` (redacts keys containing password/token/secret/code). | Remains the authorization authority on both PractiCare hops. The shared server never evaluates PractiCare permissions (no duplicated `ROLE_PERMISSIONS`). |
| `ai/registry.py` | `ALL_READERS` includes `CLINICAL_AUDITOR` for read tools. | MCP must exclude the Auditor explicitly (not inherit `ALL_READERS`). |
| Legacy `/internal/tools/practicare.*` (`main.py:2089+`) | Authenticated with the **user session token**; older semantics. | Not reused (as in plan §4). |

## 3. Conflicts / gaps in `SHARED_MCP_ARCHITECTURE_PLAN.md` and proposed resolutions

| # | Plan says | Problem | Proposed resolution |
| :--- | :--- | :--- | :--- |
| C1 | Assertion sent as header; `jti` replay cache. | One MCP operation over the SDK client = several HTTP POSTs (`initialize`, `notifications/initialized`, then `tools/list` or `tools/call`), all with the same headers. Consuming the `jti` on every POST would reject legitimate traffic. | Service token is checked on **every** `/mcp` request. The user assertion is verified and consumed **only** in the `tools/list` and `tools/call` handlers. One assertion = one operation; the Step 6 client creates a fresh assertion per operation (it already opens one MCP connection per call). Concurrent calls use different `jti`s and never interfere. |
| C2 | Service token = static secret, server stores SHA-256 hash. | Requirement: reject **expired** credentials; a static hash has no expiry. | Every registered token entry has a mandatory `not_after` (max 180 days) and optional `not_before`; several entries per app allow overlap during future rotation. Expired → 401. (Alternative considered: short-lived signed client JWT. Rejected: it would be signed with the same app key as the user assertion, i.e. not an independent second factor.) |
| C3 | Server uses `MCPServer` (+ low-level hooks). | `MCPServer.list_tools()` has no request context, so per-caller filtering needs its `middleware` API, which the SDK documents as "may change in a 2.x minor release". | Switch `server.py` to the stable low-level `Server` with `on_list_tools` / `on_call_tool` (probed, see §1). Step 2 behaviour (handshake, pin, health) unchanged. |
| C4 | Server enforces role allowlist. | Requirement: "respect existing PractiCare permissions". The server cannot evaluate them without copying `ROLE_PERMISSIONS`. | Server = coarse layer (app binding + role allowlist + schema). PractiCare gateway = final authority (roles, permissions, object policy, tenant) on the execution hop (Step 4). Assertions carry **no** permissions claim; one is ignored if present. |
| C5 | PractiCare internal API re-verifies the same assertion (Step 4). | `aud` is `shared-mcp-server`, yet PractiCare would accept it. | Acceptable and kept: PractiCare verifies its **own** signature, `iss=practicare`, `aud=shared-mcp-server`, `tool`, expiry, and its own replay cache, then reloads the user from DB. The shared server never mints user tokens (it has no signing key, so it cannot forge user context). Re-confirm in Step 4. |
| C6 | Tests for tool auth. | No business tools may exist yet. | Test-only app `testapp` + tool `testapp_echo_context` + fake adapter, defined **inside tests only**. The production registry stays empty. |
| C7 | Tenant isolation tests. | The server has no data, so a real cross-tenant read can only be tested at the PractiCare hop (Step 4). | Step 3 tests the server-side guarantees: tenant comes **only** from the verified assertion; tenant/user/role/permission arguments are rejected by schema; tenant-like headers are ignored; the adapter receives tenant only from the verified context. DB-level cross-tenant tests are in Step 4. |
| C8 | Docker exposure (Step 8). | Step 2 refuses non-loopback binding. | Keep loopback-only in Step 3. Relax only in Step 8, and only when at least one app with valid credentials is configured. |
| C9 | No silent fallback. | Fallback is a client behaviour (Step 6). | Step 3 guarantees every failure is an explicit structured error, never an empty success. The client no-fallback tests come in Step 6. |
| C11 | (found during implementation) The client creates one assertion per operation. | The SDK client's `call_tool` sends a **hidden `tools/list`** (output-schema refresh, `mcp/client/session.py:1125`) with the same connection headers. A per-connection assertion therefore fails on that second request; with single-use assertions a `call_tool` is two protected operations. | Server design unchanged. The Step 6 client must mint a fresh assertion **per HTTP request** for `tools/list` / `tools/call` (e.g. an `httpx` `Auth` flow that reads the JSON-RPC body). Proven with the official client in `tests/test_mcp_protocol.py` (`PerRequestAssertionAuth`); the static-header failure is explicit (exception), never a silent success. |
| C10 | Audit logs `tenant, user, role`. | Requirement: redact sensitive user information. | Log opaque IDs only (`user_id`, `tenant_id`, role); never names, emails, argument values or results (argument **key names** only). Claims from an assertion that **failed** verification are never logged. Redaction gains `mcpsvc_` token and email patterns. |

## 4. Design

### 4.1 Request pipeline (`/mcp`)

```
HTTP request
 └─ ServiceAuthMiddleware (ASGI, outermost on /mcp)        401 if token missing/invalid/expired
     sets scope.state.mcp_app = {app_id, token_id}
     └─ ProtocolVersionGuard (Step 2)                       400/413
         └─ SDK Streamable HTTP (DNS-rebinding protection)  421
             └─ low-level Server
                 ├─ initialize / notifications              service auth only
                 ├─ tools/list  → verify assertion(act=tools/list) → consume jti → filter → result
                 └─ tools/call  → verify assertion(act=tools/call, tool=name) → consume jti
                                  → visibility check (NOT_FOUND if hidden) → validate args (JSON Schema)
                                  → adapter.call_tool(args, CallContext(verified user)) → validate output
```
`/healthz` and `/readyz` stay unauthenticated (no data, no tool info beyond counts).

### 4.2 Service-to-service credential (Hop A: app → shared server)

- Format `mcpsvc_` + 43 chars base64url (32 random bytes). The prefix makes it detectable by secret scanners and the redactor.
- `Authorization: Bearer <token>` header only. The server stores `sha256(token)` per entry: `{token_id, sha256, not_before?, not_after}`. Lookup compares hashes with `hmac.compare_digest` against every active entry.
- Missing, malformed, unknown, not-yet-valid or expired → **HTTP 401**, identical body for every case: `{"jsonrpc":"2.0","id":null,"error":{"code":-32001,"message":"Unauthenticated","data":{"error":"UNAUTHENTICATED","correlation_id":"…"}}}`. The precise reason goes to the audit log only.
- The server holds **no secrets** for Hop A: only hashes and public keys.

### 4.3 Signed user assertion (per operation)

Header `X-MCP-User-Assertion: <JWT>` (≤ 4 KB). JOSE header: `alg=EdDSA` (Ed25519), `typ=mcp-user+jwt`, `kid`.

| Claim | Rule |
| :--- | :--- |
| `iss` | registered app id; **must equal the app authenticated by the service token** |
| `aud` | must equal `MCP_ASSERTION_AUDIENCE` (default `shared-mcp-server`) |
| `sub` / `tid` | non-empty strings ≤ 128 chars: verified user id / tenant id (set by the app from its DB-backed session, never from the model) |
| `role` | canonical role, pattern `^[A-Z][A-Z0-9_]{1,63}$` |
| `act` | `tools/list` or `tools/call`; must match the JSON-RPC method being served |
| `tool` | required when `act=tools/call`; must equal `params.name` |
| `cid` | correlation id, 8–64 chars `[A-Za-z0-9_-]`; if `X-Correlation-ID` is sent it must match |
| `jti` | 16–64 chars `[A-Za-z0-9_-]` (≥128-bit random) |
| `iat`, `exp` (+ optional `nbf`) | `exp − iat ≤ 60 s`; `iat ≤ now + 5 s`; 5 s leeway on `exp`/`nbf` |

Verification order: size and format → JOSE header (`alg` exactly `EdDSA`; `none`, `HS*` and `RS*` rejected, so no algorithm confusion) → key chosen by (`authenticated app`, `kid`) → signature (PyJWT `algorithms=["EdDSA"]`, `require=[…]`) → claims → **then** `jti` consumption. Unknown extra claims are ignored. `perms`/`permissions` are never read.

### 4.4 Replay protection

- `ReplayCache`: key `(iss, jti)` → expiry (`exp + leeway`). Atomic check-and-insert under a lock. Expired entries are purged on insert.
- Bounded at 50 000 entries. When full of unexpired entries the server **fails closed** (`MCP_UNAVAILABLE`); it never evicts live entries, since eviction would re-open replay.
- Same `jti` twice (sequentially or concurrently) → exactly one succeeds; the other gets `UNAUTHENTICATED` (audit reason `REPLAYED`). Different `jti`s never block each other.
- In-memory, so valid only for a single process: uvicorn `workers=1` (documented). Multiple replicas would need a shared store (future).

### 4.5 Authorization (deny by default)

1. No valid service token → nothing (401).
2. No valid assertion → `tools/list` and `tools/call` fail (`UNAUTHENTICATED`). No anonymous discovery.
3. Visible tools = `tool.app_id == authenticated app` **and** `role ∈ tool.allowed_roles` **and** `role ∉ EXCLUDED_ROLES` (`{"CLINICAL_AUDITOR"}` in phase 1). Unknown role → empty list.
4. `tools/call` on a tool that is not visible to this caller (other app's tool, role not allowed, Auditor, nonexistent) → the **same** `NOT_FOUND` "Unknown tool" error, so tools cannot be enumerated. Discovery and direct invocation share one `visible_tools()` function, so there is no bypass.
5. Arguments are validated against the manifest JSON Schema before any adapter call. New registry rules: input schemas must set `additionalProperties: false`; identity properties stay forbidden (Step 2); a manifest listing an excluded role fails startup.
6. The adapter receives `CallContext(correlation_id, app_id, tool_name, user_id, tenant_id, role, assertion)`, built **only** from verified data. The raw assertion is kept for forwarding in Step 5. PractiCare re-verifies everything (Step 4).

### 4.6 Errors (safe and structured)

| Situation | Response |
| :--- | :--- |
| Service credential problem | HTTP 401, JSON-RPC `-32001`, `data.error=UNAUTHENTICATED` |
| Assertion invalid / expired / wrong aud / wrong iss / iss≠app / bad signature / tool or act mismatch / replay | JSON-RPC error `-32001` `UNAUTHENTICATED` (one generic message) |
| Hidden or unknown tool | JSON-RPC `-32602` "Unknown tool" `NOT_FOUND` |
| Argument schema violation | JSON-RPC `-32602` `VALIDATION_ERROR` (JSON pointer of the failing field, no values echoed) |
| Replay cache full | JSON-RPC `-32603` `MCP_UNAVAILABLE` |
| Adapter `AdapterError` / timeout | `CallToolResult(isError=true, structuredContent={error, correlation_id})` |
| Unexpected exception | `-32603` `UPSTREAM_ERROR`, no stack trace or message details |

Every error carries `data.correlation_id` (the verified `cid`, or a server-generated `srv-*` id). Bodies never contain tokens, assertions, claims or argument values; tests assert this.

### 4.7 Audit

One redacted JSON line per decision. Events: `mcp.auth.service` (denials, plus first success per token per process), `mcp.tools.list`, `mcp.tools.call`. Fields: `ts, event, correlation_id, request_id, app, token_id, tool, tenant, user, role, decision (ALLOWED|DENIED|ERROR), reason (MISSING_TOKEN|INVALID_TOKEN|EXPIRED_TOKEN|BAD_ASSERTION|BAD_SIGNATURE|EXPIRED_ASSERTION|WRONG_AUDIENCE|WRONG_ISSUER|ISSUER_APP_MISMATCH|ACTION_MISMATCH|TOOL_MISMATCH|REPLAYED|UNKNOWN_TOOL|VALIDATION_ERROR|ADAPTER_ERROR|…), outcome, latency_ms, arg_keys, returned_tools`.
Never logged: tokens, hashes, assertions, argument values, results, names or emails, or claims from unverified assertions.

### 4.8 Credentials never reach the LLM

Credentials live only in HTTP headers created by the app's MCP client (Step 6). Tool input schemas contain no identity fields. Tool results and errors contain no credential material. The `X-MCP-User-Assertion` header and service token are never part of `tools/list` descriptions. Tests check list and call responses for token substrings.

### 4.9 Configuration

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `MCP_APPS_FILE` | unset → zero apps (every `/mcp` call = 401) | JSON with app registrations: `app_id`, `display_name`, `client_tokens[{token_id, sha256, not_before?, not_after}]`, `assertion_keys[{kid, public_key_pem}]`. Contains **no secrets** (hashes and public keys only). Local file `platform/shared-mcp-server/secrets/apps.json` is already git-ignored by the root `secrets/` rule. A committed `config/apps.example.json` uses placeholders. |
| `MCP_ASSERTION_AUDIENCE` | `shared-mcp-server` | expected `aud` |
| `MCP_ASSERTION_MAX_LIFETIME_SECONDS` | `60` (max 300) | `exp − iat` cap |
| `MCP_CLOCK_SKEW_SECONDS` | `5` (max 30) | leeway |
| `MCP_REPLAY_CACHE_MAX_ENTRIES` | `50000` | bound |

Startup refuses invalid files: bad JSON, duplicate app/token/kid, hash not 64 hex, `not_after` in the past or more than 180 days ahead, PEM not an Ed25519 public key, private key material present.

## 5. File-level implementation plan

All under `platform/shared-mcp-server/` (plus this doc and `PROJECT_STATUS.md`):

| File | Change |
| :--- | :--- |
| `requirements.txt` | add exact pins `PyJWT==2.15.1`, `cryptography==50.0.2` (already installed; made explicit) |
| `shared_mcp_server/config.py` | new settings from §4.9 |
| `shared_mcp_server/errors.py` (new) | error codes (moved from `adapters/base.py`, re-exported there), JSON-RPC codes, `McpSecurityError(code, reason)` |
| `shared_mcp_server/auth/__init__.py` (new) | package |
| `shared_mcp_server/auth/service_tokens.py` (new) | `ServiceCredential`, `ServiceTokenVerifier` (hash, constant time, validity window), `ServiceAuthMiddleware` (ASGI, 401 body, audit) |
| `shared_mcp_server/auth/assertions.py` (new) | `AssertionVerifier`, `VerifiedUser`; implements §4.3 |
| `shared_mcp_server/auth/replay.py` (new) | `ReplayCache` (§4.4), injectable clock for tests |
| `shared_mcp_server/authz.py` (new) | `EXCLUDED_ROLES`, `visible_tools(registry, app_id, role)`, `resolve_callable_tool(...)` |
| `shared_mcp_server/apps_config.py` (new) | load and validate `MCP_APPS_FILE` → `AppRegistration`s |
| `shared_mcp_server/registry.py` | `AppRegistration` gains `client_tokens`, `assertion_keys`; tool rules `additionalProperties:false` and excluded roles |
| `shared_mcp_server/adapters/base.py` | `CallContext` gains verified user fields and raw assertion (for Step 5 forwarding) |
| `shared_mcp_server/server.py` | switch to low-level `Server`; `on_list_tools` / `on_call_tool` implementing §4.5–4.7; middleware order; `build_app(settings, registry, adapters)` |
| `shared_mcp_server/audit.py` | extra value patterns (`mcpsvc_…`, emails); `arg_keys` helper |
| `config/apps.example.json` (new) | placeholder structure, no real values |
| `.env.example`, `README.md` | new variables, security model summary |
| `tests/_security_fixtures.py` (new) | per-run ephemeral Ed25519 keys and random service tokens, `make_assertion(**overrides)`, test-only `testapp` + `testapp_echo_context` + echo adapter (never real secrets) |
| `tests/test_service_auth.py` (new) | §6 rows 1–4 |
| `tests/test_assertions.py` (new) | §6 rows 5–14 (unit level) |
| `tests/test_replay.py` (new) | §6 rows 15–18 |
| `tests/test_authorization.py` (new, live HTTP) | §6 rows 19–30 |
| `tests/test_apps_config.py` (new) | config validation |
| `tests/test_audit.py`, `tests/test_registry.py`, `tests/test_mcp_protocol.py` | extended / updated (protocol tests now authenticate; unauthenticated → 401) |

No change to: `apps/**`, root `.gitignore`, `docker-compose.yml`, other platform folders, existing credentials.

## 6. Security test matrix

| # | Test | Expected |
| :--- | :--- | :--- |
| 1 | `/mcp` without `Authorization` (initialize, tools/list, tools/call, GET) | 401 `UNAUTHENTICATED`, no tool data |
| 2 | Malformed, unknown, other-app-hash, lowercase-prefix tokens | 401, same body as #1 |
| 3 | Token before `not_before` / after `not_after` | 401 (audit `EXPIRED_TOKEN`) |
| 4 | Valid token, `/healthz` and `/readyz` unaffected; 401 body contains no token text | ✓ |
| 5 | Assertion missing / empty / > 4 KB / not a JWT | `UNAUTHENTICATED` |
| 6 | Signature by a different Ed25519 key; tampered payload | `UNAUTHENTICATED` (`BAD_SIGNATURE`) |
| 7 | `alg=none`, `alg=HS256` keyed with the public key, `RS256` | rejected (algorithm confusion) |
| 8 | Expired; `nbf` in future; `iat` far in future; lifetime > 60 s | rejected |
| 9 | Wrong `aud`; missing `aud` | rejected |
| 10 | Wrong `iss`; `iss` = another registered app (app A token + app B assertion) | rejected (`ISSUER_APP_MISMATCH`) |
| 11 | Unknown `kid`; kid from another app | rejected |
| 12 | Missing each required claim; wrong claim types | rejected |
| 13 | `act=tools/list` assertion used for tools/call; `tool` ≠ called tool | rejected |
| 14 | `cid` ≠ `X-Correlation-ID` | rejected |
| 15 | Same assertion twice (sequential) | first OK, second `UNAUTHENTICATED` (`REPLAYED`) |
| 16 | Same assertion in 20 concurrent calls | exactly 1 succeeds |
| 17 | 20 concurrent calls with distinct assertions | all succeed |
| 18 | Cache full of live entries → fail closed; expired entries purged | ✓ |
| 19 | Discovery per role: Owner/Manager/Doctor/Nurse see allowed test tools; **Auditor sees none**; unknown role sees none | ✓ |
| 20 | Direct `tools/call` by Auditor / disallowed role / other app's tool / nonexistent tool | identical `NOT_FOUND`, adapter never called |
| 21 | Manifest that lists `CLINICAL_AUDITOR` or lacks `additionalProperties:false` | startup error |
| 22 | Cross-tenant: tenant-A assertion with `tenant_id`/`tid`/`user_id`/`role`/`permissions` arguments for tenant B | `VALIDATION_ERROR`, adapter not called |
| 23 | Cross-tenant: `X-Tenant-ID: tenant-B` header / forged body fields | ignored; adapter receives tenant A only |
| 24 | Adapter receives exactly the verified `sub/tid/role/cid` | ✓ |
| 25 | Role alias (`NURSE`, `DOCTOR`) in assertion | not canonical → no tools |
| 26 | Arguments schema violation | `VALIDATION_ERROR`, no values echoed |
| 27 | Adapter raises `AdapterError(TIMEOUT)` / unexpected exception | structured error with correlation id, no stack trace |
| 28 | Audit lines per decision contain correlation id, app, tool, decision, reason | ✓ |
| 29 | Secret redaction: no token, assertion, argument value or email in any audit line or error body | ✓ |
| 30 | Step 2 guarantees still hold with auth (pin, 413, Host check, health) | ✓ |

Regression: PractiCare 182/182 and frontend `tsc --noEmit` re-run (expected unchanged; no app files touched).

## 7. Explicitly out of scope for Step 3

PractiCare assertion signer and MCP client (Step 6); PractiCare internal API and DB-backed re-verification, the **final** tenant/role authority (Step 4); PractiCare adapter and Hop B token (Step 5); business tools; LangGraph; Docker/deployment; credential generation tooling (Step 8, with key generation documented then).

## 8. Decisions requested

1. Service credential: static `mcpsvc_` token with mandatory expiry window (**recommended**) vs short-lived signed client JWT.
2. App registrations in a git-ignored JSON file `secrets/apps.json` (**recommended**) vs individual environment variables.
3. Single-use assertions for `tools/list` as well as `tools/call` (**recommended**).
4. Assertion lifetime cap 60 s, clock skew 5 s (**recommended**).
5. Switch to the low-level SDK `Server` API (**recommended**, conflict C3).
6. Hidden/forbidden tool → `NOT_FOUND`, indistinguishable from nonexistent (**recommended**) vs explicit `FORBIDDEN`.
7. Hop A middleware: custom `ServiceAuthMiddleware` (**recommended**: JSON-RPC 401 body per §4.2, `not_before`/`not_after` per token) vs the SDK's built-in `mcp.server.auth.middleware.bearer_auth` (`BearerAuthBackend` + custom `TokenVerifier`). The SDK option is oriented to OAuth 2.1 resource servers (`resource_server_url`, RFC 9728 `WWW-Authenticate` metadata); it means less custom code, but a different 401 shape.

## 9. Re-verification log (2026-10-18, read-only)

Re-checked against the working tree before review; no code changed:
- Server venv: `mcp 2.3.0`, `PyJWT 2.15.1`, `cryptography 50.0.2`, `jsonschema 4.26.0`, `starlette 1.8.0`. `requirements.txt` does not yet pin PyJWT/cryptography (the §5 change adds the pins).
- SDK: low-level `Server(on_list_tools=…, on_call_tool=…)` exists (`mcp/server/lowlevel/server.py`); `MCPServer` middleware is documented as "may change in a 2.x minor release" (`mcp/server/mcpserver/server.py:285`) → C3 confirmed. `ClientSession.initialize()` sends `initialize`, then a separate `notifications/initialized` (`mcp/client/session.py:651,671`) → C1 confirmed.
- PractiCare: `ALL_READERS` includes `CLINICAL_AUDITOR` (`ai/registry.py:70`); `ROLE_ALIASES` (`ai/context.py:192`); gateway forces `tenant_id` and pops `user_id`/`user_role`/`permissions` (`ai/gateway.py:127-131`); `get_request_context` (`main.py:94`); legacy `/internal/tools/practicare.*` (`main.py:2089`).
- `platform/shared-mcp-server/secrets/apps.json` is git-ignored (`.gitignore:32 secrets/`).

## 10. Implementation record (2026-10-18)

Approved conditions and where each is enforced:

| Condition | Enforcement | Tests |
| :--- | :--- | :--- |
| Every `/mcp` request authenticates the calling app | `ServiceAuthMiddleware` wraps the whole MCP mount (unknown paths, GET/DELETE included) | `test_service_auth.py` |
| `initialize` / notifications do not consume the assertion | assertion verified only in `on_list_tools` / `on_call_tool` | `test_authorization.py::test_initialize_and_notifications_do_not_consume_the_assertion`, official-client handshake test |
| Each protected operation has its own signed assertion | `act` + `tool` binding, single-use `jti` | `test_assertions.py`, `test_replay.py`, C11 tests |
| Identity/tenant/role never from tool arguments | `additionalProperties:false` required, identity property names refused (normalized: `tenantId`, `TID`, `sub`…), runtime JSON Schema check, headers ignored | `test_registry.py`, `test_authorization.py` |
| PractiCare remains the final authority | no permission evaluation in the server; raw assertion forwarded in `CallContext` for Step 4 re-verification | `test_authorization.py::test_allowed_call_receives_only_verified_identity` |
| Deny by default (discovery and invocation) | one `visible_tools()` for both; `NOT_FOUND` for hidden/forbidden/unknown | `test_authorization.py` |
| Clinical Auditor excluded | `EXCLUDED_ROLES`, startup error if a manifest lists it | `test_registry.py`, discovery/invocation tests |
| Replay protection single-worker only | documented in `auth/replay.py`, README, `.env.example`, startup audit line; `workers=1` in `__main__.py` | `test_replay.py` |
| No silent fallback | every failure is an explicit JSON-RPC error or `isError` result; client-side no-fallback tests remain Step 6 | all error-path tests |
| No real credentials in Git | per-run ephemeral keys/tokens in tests; `config/apps.example.json` placeholders (test asserts no real token/hash/PEM); real file under git-ignored `secrets/` | `test_apps_config.py` |

Stricter than the design text (deliberate):
- Lifetime cap and skew are **hard limits** (`≤ 60 s`, `≤ 5 s`), refused at startup if larger (design allowed up to 300/30).
- `aud` must be a single string (arrays refused); `sub`/`tid` may not contain `@` (no emails as ids).
- JOSE headers `jwk`, `jku`, `x5u`, `x5c`, `crit` are refused.
- The issuer is bound to the authenticated app **before** key selection (audit reason `ISSUER_APP_MISMATCH`).
- A token hash registered for two apps is a startup error.
- Additional audit reasons: `MISSING_ASSERTION`, `BAD_ALGORITHM`, `UNKNOWN_KEY`, `CORRELATION_MISMATCH`, `LIFETIME_TOO_LONG`, `IAT_IN_FUTURE`, `ASSERTION_NOT_YET_VALID`, `TOKEN_NOT_YET_VALID`, `REPLAY_CACHE_FULL`, `UNEXPECTED_ERROR`.

Results: shared server **135/135** (43 Step 2 tests kept/updated + 92 new), stable over 3 runs; PractiCare regression **182/182** (throwaway container from the backend image, repo mounted read-only, no network); PractiCare frontend `tsc --noEmit` exit 0; entry-point smoke test (0.0.0.0 refused, invalid apps file refused, default start = 0 apps and `/mcp` 401).

Still open for later steps: shared replay store before multi-worker (Step 8); credential generation tooling (Step 8); PractiCare re-verification and DB-level cross-tenant tests (Step 4); per-request assertion minting and no-fallback tests in the client (Step 6).
