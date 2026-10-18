# PROJECT_STATUS.md - Shared MCP MOC Implementation Status

**Last Updated**: 2026-10-18  
**Current Status**: Inventory AI round 1 and Inventory Stabilization round 2 **deployed to the local MOC** (round 2: 2026-10-18 ~13:41 IST) and verified automatically | **Live manual verification per role pending**

## 000000. 2026-10-18 — Shared MCP Step 2: server foundation (dev repo only, not deployed)
- Location `D:\Axio360\shared-mcp-development`, branch `feature/shared-mcp-step2`; all code in `platform/shared-mcp-server/` (see its README). Not pushed, not deployed, no Docker service.
- SDK verified: no `mcp` package existed in the shared `.venv` or the backend images; installed `mcp==2.3.0` (+ `mcp-types 2.3.0`, latest on PyPI) into a git-ignored venv `platform/shared-mcp-server/.venv` (Python 3.12.10). SDK 2.3.0 handshake versions: 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25; separate stateless era 2026-07-28.
- Implemented: `MCPServer` + Streamable HTTP (`/mcp`, stateless, JSON responses), protocol pinned to `2025-11-25` by `ProtocolVersionGuard` (other versions/missing header → 400; 2026-07-28 era blocked; body > 256 KB → 413), `/healthz`, `/readyz` (503 until the session manager runs), loopback-only config, validated empty app/tool registry, redacting JSON audit log, `AppAdapter` interface. No tools, no auth, no PractiCare client, no LangGraph change.
- Tests: server suite **43/43** (official SDK client handshake + `tools/list == []` over real HTTP on 127.0.0.1; wire-level version rejection; health/readiness; config; registry; audit redaction; adapter interface). Entry-point smoke test: `0.0.0.0` refused (exit 2), bound to 127.0.0.1 only. PractiCare regression **182/182**; frontend `tsc --noEmit` OK.
- MOC, its containers and DB, and the archived test copy unchanged.
- Next step: Step 3 (authentication: service tokens, user assertions, per-tool role allowlist) — awaiting approval.

## 00000. 2026-10-18 — Shared MCP Step 1: isolated baseline & readiness (test copy only)
- Test copy `D:\Axio360\practicare-staging` (branch `master`): Round 2 committed as `d477ae6`; MOC frontend loading fix (`next.config.ts`, `page.tsx`, PROJECT_STATUS §000) and `docs/SHARED_MCP_ARCHITECTURE_PLAN.md` synced byte-exact as `d71d671`; working tree clean. PractiCare source now identical to the MOC (only `.env`, `practicare_fallback.db`, `backend.zip` intentionally not copied).
- Backups: `D:\Axio360\backups\step1-mcp-baseline-20261018-190418\` (MANIFEST.json, SHA256SUMS, MOC + test-copy file archives, Round 2 patch) — verified.
- Checks (test copy, in-memory SQLite): **182/182 tests**, 29 backend files parse, 14 core modules import, `tsc --noEmit` OK, ESLint `page.tsx` 60 problems (was 62; fix removed 2), new components clean. `next build` not runnable: test-copy `node_modules` is a junction to the MOC's host `node_modules` (no writes occurred).
- Running MOC, database and other apps untouched. Step 2 not started (awaiting approval).

## 0000. 2026-10-18 — Shared MCP Server: architecture audit & phase 1 plan (PLAN ONLY, awaiting approval)
- Plan: `docs/SHARED_MCP_ARCHITECTURE_PLAN.md` (current flow mapped to file/function; proposed design; security; 3 read-only tool contracts; Docker; implementation and test plan; future app onboarding).
- Verified facts: official SDK `mcp` 2.3.0 (2026-10-02) dependencies are satisfied by the backend image; protocol pin `2025-11-25` is supported by SDK 2.3.0 and 1.30.0; `platform/` and `packages/` scaffolds are empty.
- Nothing implemented; no code, container, or database changes. Open decisions listed at the end of the plan.

## 000. 2026-10-18 — Frontend UI Loading & Chunk Connection Reset Fix (APPLIED to local MOC)

### Fix Record
| Check / Step | Result |
| :--- | :--- |
| **Symptom** | Browser stuck on infinite spinning circle (`<RefreshCw className="animate-spin" />`) at `http://localhost:3001` with DevTools console error: `Failed to load resource: net::ERR_CONNECTION_RESET` on Next.js chunk `1q96_modules_...react-dom_...js`. |
| **Root Cause 1** | In `apps/practicare/frontend/next.config.ts`, experimental `cacheComponents: true` and `partialPrefetching: true` (PPR) caused Turbopack dev server streaming connection resets over Docker port mappings on Windows. |
| **Root Cause 2** | In `apps/practicare/frontend/src/app/page.tsx`, `isSessionChecked` had no fallback or timeout guard; if React hydration was interrupted or delayed, the UI was trapped indefinitely on the initial SSR loading spinner. |
| **Modifications** | 1. Removed experimental `cacheComponents` and `partialPrefetching` from `next.config.ts`.<br>2. Added a 2-second timeout fallback in `page.tsx` session restoration `useEffect`.<br>3. Upgraded loading screen with an informative status label and an interactive "Continue to Portal" button.<br>4. Fixed unescaped apostrophes in `page.tsx` line 3316. |
| **Verification** | 1. Next.js server automatically reloaded cleanly (`Ready in 786ms`).<br>2. `docker exec moc-practicare-ui npx tsc --noEmit` passed with 0 errors.<br>3. `GET http://localhost:3001` returns 200 OK in ~40ms and all chunks load reliably.<br>4. Regression test suites run and confirmed passing. |
| **Status** | **Integrated, running, and verified on local MOC container.** |

---

## 00. 2026-10-18 — Inventory Stabilization Round 2 (DEPLOYED to local MOC)

### Deployment record (approved by user, local MOC only)
| Check / Step | Result |
| :--- | :--- |
| Target | `D:\Axio360\shared-mcp-moc`, compose project `shared-mcp-moc`, Postgres `moc-postgres-db` (localhost:5433). No staging/production touched. |
| Bundle | 12 files; all match the SHA-256 manifest and the tested test-copy files; LF only. |
| Source drift | None: the 10 MOC files replaced were byte-identical to the tested baseline; the 2 new files were absent. |
| Backup | `D:\Axio360\backups\practicare-moc-db-predeploy-v2-20261018-134118.sql`, validated by restore into a throwaway Postgres (internal network, removed): restore OK, counts match on 10 tables. Source backup: `practicare-moc-src-pre-inventory-v2-20261018.tar.gz`. |
| Deploy | Bundle extracted byte-exact; 12/12 MOC files match the manifest. No migration, no schema change. |
| Restarts | Only `moc-practicare-backend` (same image, no rebuild) and `moc-practicare-ui`. |
| Data integrity | All 13 table fingerprints identical before/after; full-column fingerprint of the 18 inventory items and 2 import records identical. |
| Backend | `/health` 200, DB connected; OpenAPI now has `POST /api/v1/inventory/{item_id}/adjust`, `search` param, `stock_status`/`expiry_state`/`shortfall`/`can_manage`; approval prepare hooks on `update_inventory_item` and `adjust_inventory_stock`. Clean startup log. |
| Frontend | http://localhost:3001 → 200; compiled chunk contains the Edit / Adjust modals, search box and status badges. |
| Live read-only role check (tenant-easternwav-cd6b, GET only) | Owner & Manager: `can_manage=true`, all 5 inventory write tools exposed; Doctors & Nurse: `can_manage=false`, no write tools. Statuses: Examination Gloves Low Stock / Expiring Soon; Hand Sanitizer In Stock / Expiring Soon; search and expiry filters correct; dashboard low-stock 1, expiring-soon 3. |
| Regression tests (MOC tree, in-memory SQLite) | **182/182 passed** |
| Live manual testing | **Not yet done** |

**Rollback**: restore `practicare-moc-src-pre-inventory-v2-20261018.tar.gz` into the MOC, delete the 2 new files (`frontend/src/app/InventoryEditModals.tsx`, `tests/test_inventory_stabilization.py`), restart backend + UI. No DB rollback needed (no schema change); last-resort data restore: `practicare-moc-db-predeploy-v2-20261018-134118.sql`.

### Implementation summary

| Status legend | |
| :--- | :--- |
| Implemented in isolated test copy | Yes (`D:\Axio360\practicare-staging`, working tree on top of baseline commit `69c607e` = what is deployed) |
| Deployed to local MOC | **Yes**, 2026-10-18 ~13:41 IST (see deployment record above). |
| Verified through automated tests | Yes: **182/182** (155 previous + 27 new in `tests/test_inventory_stabilization.py`); frontend `tsc --noEmit` passes; ESLint: new components clean, `page.tsx` 62 problems = identical to baseline (pre-existing) |
| Verified on real data | Yes, on a throwaway restore of a fresh MOC dump (internal network, removed): Nitrile Gloves not-found message, independent statuses, restock/update approval previews, NOT_FOUND / AMBIGUOUS_ITEM refusals |
| Verified through live manual testing | **No** |

**Fixes / features**
1. **False "all adequately stocked" claim** — root cause: `get_inventory_status` built its `message` from alerts of the *returned* items only, so a search with no matches produced the server-written sentence "All N inventory items are adequately stocked", which Gemini repeated. Now the message describes only what was returned (exact not-found wording), catalog-wide counts are separate, and an agent guard removes any "all stocked / no low stock" claim that contradicts the latest tool result and adds the not-found statement if the model omits it.
2. **Stock vs expiry status** — root cause: a single `stock_status: "OK"` ignored expiry. Now independent server values: `stock_status` (In Stock / Low Stock / Out of Stock), `expiry_state` (Expired / Expiring Soon ≤30 days / Valid / No Expiry Date), plus quantity, threshold, shortfall, expiry date, days to expiry, location — in AI tool results, REST and UI badges.
3. **Manual Owner/Manager management** — Edit modal (prefilled, validated, only changed fields sent, stock change needs a confirm click, optimistic-concurrency `expected_current_stock` → 409 instead of silent overwrite); Restock/Reduce modal with current → new preview and confirm step; new atomic `POST /api/v1/inventory/{id}/adjust` (conditional UPDATE … RETURNING, never negative); search by name/supplier/batch; per-item `can_manage` flag drives the UI; REST writes and denied attempts audited (`rest:inventory.*` in `ai_audit_events`).
4. **AI chat management** — update/adjust accept `item_id` or `item_query` (name) resolved against real tenant records; ambiguous → `AMBIGUOUS_ITEM` with candidates, missing → `NOT_FOUND`, never auto-created; approval cards show verified old → new values / current, change, new quantity; approved values are pinned and execution refuses if the record changed meanwhile; agent blocks `create_inventory_item` unless the user explicitly asks to create.
5. **Database verification (Step 7)** — `inv-5c64a3e0` "Test Face Shields" exists in `tenant-easternwav-cd6b`: 25 pieces, expiry 2027-06-30, min threshold 10 (default), supplier/batch/price/room empty; audit shows `create_inventory_item` ALLOWED by CLINIC_OWNER at 2026-10-18 07:35:57 UTC (an earlier Doctor attempt was BLOCKED).

**Behaviour changes**: invalid AI adjustments (below zero, unknown/other-tenant item, ambiguous name) are refused before any approval is created; approval texts changed; no schema change and no migration.

**Bundle** (applied): `D:\Axio360\backups\practicare-moc-inventory-stabilization-20261018-inventory-v2-files.tar.gz` (12 files, SHA-256 manifest `…-files.sha256`, `.patch`).

**Next step**: live manual testing per role (Owner, Manager, Doctor, Nurse), then — after user approval — Shared MCP Server design.

---

## 0. 2026-10-18 — Inventory AI Features & Task Permission Fixes (DEPLOYED to local MOC)

### Deployment record (approved by user, local MOC only)
| Check / Step | Result |
| :--- | :--- |
| Target | `D:\Axio360\shared-mcp-moc`, compose project `shared-mcp-moc`, Postgres `moc-postgres-db` (localhost:5433). No staging/production touched. |
| Backup | `D:\Axio360\backups\practicare-moc-db-predeploy-20261018-123513.sql`, validated by restoring into a throwaway Postgres (internal network, removed): restore OK, all table counts match. Source backup: `practicare-moc-src-pre-inventory-20261018.tar.gz`. |
| Bundle integrity | 18 files byte-identical to the tested test-copy files (LF); the 14 replaced MOC files were byte-identical to the tested base; 4 new files. |
| Startup/seed review | Seeding inserts only when demo practices/users are missing; UPDATEs only fill NULLs (unchanged code). No data effect on the current DB. |
| Migration 003 | Applied manually (single transaction, committed); 3 nullable columns + `inventory_imports` table present. |
| Restarts | `moc-practicare-backend` restarted (same image; code bind-mounted; no new dependencies, no rebuild). `moc-practicare-ui` restarted. No other containers touched. |
| Data integrity | Per-table row count + md5 fingerprint of all 13 PractiCare tables (pre-existing columns) **identical before and after** deployment. 11 inventory items intact, new columns NULL; `inventory_imports` empty. |
| Backend | `/health` 200, database_connected=true; OpenAPI exposes `/api/v1/inventory/import/extract`, `/import/confirm`, `expiry`/`sort` params; registry has 6 inventory AI tools. Startup log clean. |
| Frontend | http://localhost:3001 → 200; compiled client chunk contains the new Inventory UI (Import with AI, expiry filters, sort). |
| Live read-only smoke | Real tenants: task lists/flags per role, dashboard counts equal list counts; tenant-001 expiry filters correct for every role (3 items ≤30 days = dashboard count). |
| Regression tests (MOC tree, in-memory SQLite) | **155/155 passed** |
| Gemini | `GOOGLE_API_KEY` present in backend env (value not printed); model `gemini-3.1-flash-lite`. |

**Rollback**: restore `practicare-moc-src-pre-inventory-20261018.tar.gz` into the MOC and restart backend + UI (old code ignores the new nullable columns). Optional schema removal: commented DROP statements at the end of `migrations/003_inventory_import_fields.sql`. Full data rollback (last resort): restore `practicare-moc-db-predeploy-20261018-123513.sql`.

### Implementation summary
Built and verified in `D:\Axio360\practicare-staging` (isolated test copy). The MOC source tree, the running Docker services and the MOC PostgreSQL database are **unchanged**. Deployment bundle: `D:\Axio360\backups\practicare-moc-inventory-tasks-20261018-inventory-v1-files.tar.gz` (+ `.patch`), 18 files; the MOC base files were verified byte-identical to the bundle's base.

| Area | Status |
| :--- | :--- |
| **AI inventory import** (PDF / image / text → Gemini extraction → editable preview with missing/ambiguous/low-confidence flags → explicit confirmation → server-side re-validation → one transaction; single-use import token; duplicate lot detection; created/updated/skipped/rejected report; restock never overwrites existing values) — `inventory_service.py`, `main.py` (`/api/v1/inventory/import/extract`, `/confirm`), `InventoryImportModal.tsx` | Implemented; automated tests pass; real Gemini extraction **not** live-verified (tests use a scripted model) |
| **Expiry filters & sort** (all / expired / ≤7 / ≤30 / ≤90 days / no expiry; nearest-expiry sort; server-computed `days_to_expiry`, `expiry_status`) — `GET /api/v1/inventory?expiry=&sort=`, Inventory tab | Implemented; verified on a throwaway restore of real data |
| **Inventory via AI chat** — tools `create_inventory_item`, `update_inventory_item`*, `adjust_inventory_stock`*, `preview_inventory_import`, `confirm_inventory_import`* (*approval required); Owner/Manager only; Doctor/Nurse read-only via `get_inventory_status` (expiry filters, item details); questions are hard-blocked from write tools (schema filtering + execution guard + audit); unverified inventory success claims replaced | Implemented; automated tests pass; live Gemini chat not verified |
| **Doctor delete bug** — root cause: Doctor delete policy never checked creator identity, so any Doctor could delete any other Doctor's / legacy (no-creator) Doctor-or-Nurse-scope task. New rule: Doctor deletes only tasks they created that are unassigned or assigned to a Nurse | Fixed in `ai/policy.py`; flags and API agree (tested per task) |
| **Manager→Doctor reassignment** — not reproducible with the current code via REST (assignee-based scope fix of 2026-10-18 already applies); residual causes fixed: staff free-text label overrode the linked user's verified role; AI `list_tasks` applied its limit before the visibility filter | Fixed; regression tests + real-data check pass |
| **Migration 003** (`migrations/003_inventory_import_fields.sql`: nullable `supplier`, `batch_number`, `purchase_price NUMERIC(12,2)`, new `inventory_imports` table; also applied by `init_db_and_seed()` on startup) | Verified on throwaway restore (idempotent, data unchanged); **applied to the MOC DB on 2026-10-18** |

**Tests**: 155/155 (115 existing + 40 new in `tests/test_inventory_ai_and_task_permissions.py`); frontend `tsc --noEmit` passes. Two existing tests were updated for the stricter Doctor-delete policy (fixtures now record `created_by_user_id`; legacy no-creator task no longer Doctor-deletable).

**Behaviour change to note**: legacy tasks with no recorded creator can no longer be deleted by Doctors (Owner/Manager still can).

**Next step**: live manual verification per role (real PDF/image extraction with Gemini, inventory chat flows and approval cards, Doctor delete buttons). Then begin Shared MCP Server integration.

---

## 1. Verified Regression Test Suites

Two distinct test suites are tracked in the repository. Both have been directly executed and verified passing against isolated SQLite environments:

| Test Suite | Tests Run | Result | Scope & Coverage |
| :--- | :---: | :---: | :--- |
| **Core Stabilization Suite** | **43** | **43 / 43 PASSED** | Core role hierarchy (`test_stabilization_permissions.py`: 30), Tool Gateway 6-step checks (`test_verified_execution_and_rbac.py`: 3), REST CRUD (`test_practicare_crud.py`: 4), and Phase 0 native auth (`test_phase0_security.py`: 6). |
| **Full Regression Suite** | **115** | **115 / 115 PASSED** | Complete `tests/` suite covering permission stabilization (30), security authorization regressions (26), manual test automated mirrors (27), identity & leave isolation (14), runtime role regressions (11), CRUD (4), and verified execution (3). |

*Note: While automated regression tests pass at 100%, end-to-end manual testing across all 4 user roles in live browsers is still pending before claiming full demo readiness or complete AI/REST operational parity.*

---

## 2. Recent Fixes & Implementation Verification Status

Verification Status Legend:
- **Source Code**: Implemented in backend/frontend modules.
- **Integrated**: Connected to REST API, Tool Gateway, and UI states.
- **Running**: Verified in automated test executions.
- **Manually Verified**: Confirmed via live interactive user sessions.

| Feature / Fix Area | Description & File Targets | Implementation Status |
| :--- | :--- | :--- |
| **AI Evidence Grounding** | Quotes clinical notes directly from DB records; eliminated canned fallback hallucinations; refined intent regex boundaries (`\b(?:assign|reassign)\b`, `\b(?:tick|untick|toggle|complete)\b`) to prevent false assignment warnings on identifiers. (`ai/agent.py`) | **Integrated & Running** *(Manual live chat verification in progress)* |
| **Room Read-Only Safety** | Nurses strictly restricted to read-only room viewing; turnover updates restricted to Doctors, Managers, and Owners; room creation restricted to Owners/Managers. (`ai/policy.py`, `ai/handlers/operations.py`, `frontend/src/app/page.tsx`) | **Integrated & Running** *(REST & AI test verified; manual UI pending)* |
| **Checklist Persistence** | Database-backed checklist definition, assignment, and status updates via SQLAlchemy session with rollback guards; company-wide visibility for nurses with self-only item completion. (`models.py`, `ai/handlers/checklists.py`, `main.py`) | **Integrated & Running** *(Automated DB verified; manual UI pending)* |
| **Delegated Task Visibility** | Doctors can view and track tasks assigned to nurses within their clinical scope; higher-tier tasks created by Owners/Managers are isolated from Doctor queries. (`ai/policy.py`, `ai/handlers/tasks.py`) | **Integrated & Running** *(Scope tests passing; multi-user live UI pending)* |
| **Hierarchical RBAC Enforcement** | Enforces $\text{OWNER} > \text{MANAGER} > \text{DOCTOR} > \text{NURSE}$ across REST routers and Tool Gateway; self-deletion prohibited for Managers and Doctors; creator lineage tracked via `created_by_user_id` and `created_by_role`. (`ai/policy.py`, `migrations/002_role_hierarchy_lineage.sql`) | **Integrated & Running** *(All 30 permission tests passing)* |

---

## 3. Current AI Implementation & Parity Status

- **Agent Framework**: Gemini 3.1 Flash-Lite + LangGraph StateGraph (`apps/practicare/backend/ai/agent.py`).
- **Tool Pipeline**: 14 clinical tools registered in `apps/practicare/backend/ai/registry.py` executing through the Tool Gateway 6-step verification pipeline (Schema, Tenant, Policy, Approval, DB Persistence, Audit).
- **Parity Status**: High automated parity across core task, checklist, inventory, and room flows; live end-to-end multi-role validation is underway to confirm true production parity.

---

## 4. Remaining Issues & Ecosystem Gaps

1. **PractiCare AI & UI Edge-Cases**: Complete remaining multi-turn dialogue tests and live manual role validation (Owner, Manager, Doctor, Nurse) in browser sessions.
2. **Scaffolded Applications**: `apps/taxsnap`, `apps/propsights`, and `apps/onscribe` frontends and backends are operational, but their `agent/` and `tools/` directories remain empty.
3. **Platform Infrastructure**: `platform/shared-mcp-server`, `platform/tool-registry`, `platform/ai-tool-gateway`, and `packages/mcp-client` are scaffolded but unpopulated.

---

## 5. Next Step

**Finish remaining PractiCare AI fixes and role-based manual testing, then begin Shared MCP Server integration.**
