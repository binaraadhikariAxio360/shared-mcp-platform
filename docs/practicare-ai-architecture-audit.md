# PractiCare AI Subsystem — Full Architecture Audit & Quality Assessment

**Target:** `apps/practicare/backend/ai/` and integration points (`main.py`, `models.py`, `database.py`, `security.py`, `schemas.py`)  
**Auditor:** Senior Software Architect & Principal AI Engineer  
**Date:** October 2026  
**Status:** Audit Completed / Baseline Verified

---

## 1. Executive Summary

This architecture audit evaluates the PractiCare AI subsystem within the `shared-mcp-moc` repository. PractiCare AI provides clinical operational intelligence, task scheduling, room turnover tracking, inventory alerting, and governance-controlled automation using Google Gemini 3.1 Flash-Lite, LangGraph autonomous agent orchestration, FastAPI, and PostgreSQL with SQLAlchemy.

All baseline test suites were executed and verified at 100% pass rate before initiating any refactoring:
- `tests/test_practicare_ai.ps1` (11/11 tests passed)
- `tests/test_phase2_doctor_scenarios.ps1` (10/10 scenarios passed)
- `tests/test_staff_status_and_ui_cleanup.ps1` (9/9 suites passed)
- `tests/test_ai_privacy_and_tools.ps1` (All privacy & isolation tests passed)
- `tests/test_room_resolution.ps1` (6/6 tests passed)

While the subsystem functions robustly from an external perspective, internal code quality, modularity, and SOLID adherence exhibit notable architectural debt. The refactoring strategy focuses on safe, modular extraction without breaking backward-compatible tool contracts, public APIs, or security boundaries.

---

## 2. Current Architecture & Request Execution Flow

### 2.1 Component Overview

```
                      +------------------------------------+
                      |     Client / Frontend (Next.js)    |
                      +-----------------+------------------+
                                        | POST /api/v1/ai/chat (Bearer Token / Tenant Headers)
                                        v
                      +-----------------+------------------+
                      |         FastAPI Route Handler      |
                      |  - Authenticates user & tenant     |
                      |  - Enforces conversation privacy   |
                      |  - Loads persistent chat history   |
                      +-----------------+------------------+
                                        |
                                        v
                      +-----------------+------------------+
                      |    ai.context.SecurityContext      |
                      | (tenant_id, user_id, user_role)   |
                      +-----------------+------------------+
                                        |
                                        v
+---------------------------------------+---------------------------------------+
| PractiCareLangGraphAgent (StateGraph in ai/agent.py)                          |
|                                                                               |
|   [START]                                                                     |
|      |                                                                        |
|      v                                                                        |
|  (agent_reasoning) <-------------------------------------+                    |
|      |  - Executive data boundary check (validate_sensitive_query)            |
|      |  - Retrieve authorized schemas from registry.get_schemas_for_role()   |
|      |  - Invoke Gemini 3.1 Flash-Lite (or deterministic engine fallback)     |
|      |                                                                        |
|      +---[if blocked/failed/no tools]---> (report_synthesis) ----> [END]     |
|      |                                                                        |
|      v [tools planned]                                                        |
|  (tool_execution)                                                             |
|      |  - Zero-Trust Execution via gateway.execute()                          |
|      |  - RBAC verification                                                   |
|      |  - Argument Pydantic schema validation                                 |
|      |  - High-risk check: if approval required -> return token & HALT         |
|      |                                                                        |
|      v                                                                        |
|  (result_analysis)                                                            |
|      |  - Evaluates search results (room/staff ambiguity, 0 matches)          |
|      |  - Determines if corrective tool needed (loop limit <= 3)               |
|      |                                                                        |
|      +---[more tools needed]------------> (agent_reasoning)                   |
|      |                                                                        |
|      v [finished or limits reached]                                           |
|  (report_synthesis)                                                           |
|      |  - Synthesizes intent-aware output (action confirmation,               |
|      |    retrieval list, explanation, analysis, or executive report)         |
|      |                                                                        |
|      v                                                                        |
|    [END]                                                                      |
+---------------------------------------+---------------------------------------+
                                        | Tool invocation
                                        v
                      +-----------------+------------------+
                      |      ai.gateway.ToolGateway        |
                      |  - Zero-trust caller verification  |
                      |  - Force tenant_id anti-spoofing   |
                      |  - Strict RBAC check               |
                      |  - Intercept HIGH-risk approvals   |
                      |  - Audit logging per tenant        |
                      +-----------------+------------------+
                                        |
                                        v
                      +-----------------+------------------+
                      |        ai.tools Handlers           |
                      |  - 11 monolithic handlers          |
                      |  - Direct database queries         |
                      +-----------------+------------------+
                                        |
                                        v
                      +-----------------+------------------+
                      |       PostgreSQL Database          |
                      +------------------------------------+
```

---

## 3. Authoritative Tool Inventory

| Tool Name | Purpose | Input Schema | Handler | Required Permissions | Risk Level | Approval Req. | R/W Class | Registration Location | Actual Usage |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| `get_team_task_performance` | Aggregate team KPIs, completion rates, overdue tasks, role-scoped workloads | `GetTeamTaskPerformanceArgs` | `execute_get_team_task_performance` | `tasks:read` | LOW | No | Read | `ai/registry.py` | High (Reports, Analytics) |
| `get_room_turnover_status` | Exam & procedure room turnover status, cleaning alerts | `GetRoomTurnoverStatusArgs` | `execute_get_room_turnover_status` | `rooms:read` | LOW | No | Read | `ai/registry.py` | High (Facility monitoring) |
| `create_clinical_task` | Create new clinical task assigned to room and staff | `CreateClinicalTaskArgs` | `execute_create_clinical_task` | `tasks:write` | MEDIUM | No | Write | `ai/registry.py` | High (Task scheduling) |
| `update_checklist_status` | Update or toggle status of sterilization & hygiene checklists | `UpdateChecklistStatusArgs` | `execute_update_checklist_status` | `checklists:write` | MEDIUM | No | Write | `ai/registry.py` | Medium (Hygiene management) |
| `delete_clinical_checklist` | Destructive checklist deletion requiring human approval | `DeleteClinicalChecklistArgs` | `execute_delete_clinical_checklist` | `checklists:delete` | HIGH | **Yes** (HITL) | Write | `ai/registry.py` | Tested (Destructive governance) |
| `search_rooms` | Resolve room display numbers, names, or IDs to database primary key | `SearchRoomsArgs` | `execute_search_rooms` | `rooms:read` | LOW | No | Read | `ai/registry.py` | High (Entity resolution) |
| `search_staff` | Resolve provider names, roles, or IDs to database primary key | `SearchStaffArgs` | `execute_search_staff` | `staff:read` | LOW | No | Read | `ai/registry.py` | High (Entity resolution) |
| `list_tasks` | Retrieve clinical tasks with filtering by status, priority, staff, room | `ListTasksArgs` | `execute_list_tasks` | `tasks:read` | LOW | No | Read | `ai/registry.py` | High (Task querying) |
| `update_task_status` | Update status, priority, description, or staff assignment | `UpdateTaskStatusArgs` | `execute_update_task_status` | `tasks:write` | MEDIUM | No | Write | `ai/registry.py` | High (Task lifecycle) |
| `get_inventory_status` | Inspect medical supply stock levels, low-stock alerts, expiring items | `GetInventoryStatusArgs` | `execute_get_inventory_status` | `inventory:read` | LOW | No | Read | `ai/registry.py` | High (Supply tracking) |
| `get_practice_summary` | Executive high-level operational summary across rooms, tasks, staff, supply | `dict` (No args) | `execute_get_practice_summary` | `tasks:read` | LOW | No | Read | `ai/registry.py` | Medium (Dashboard overview) |

---

## 4. Code Quality & Architecture Audit Findings

### Summary by Severity
- **CRITICAL:** 0
- **HIGH:** 1
- **MEDIUM:** 6
- **LOW:** 4

---

### Finding 1: Staff Account Status (`is_active`) Conflated with Shift Status (`on_shift`)
- **Severity:** HIGH
- **Affected File:** `apps/practicare/backend/ai/tools.py`
- **Relevant Functions:**
  - `execute_get_practice_summary` (line 875): `on_shift_staff = sum(1 for s in staff if s.is_active)`
  - `execute_get_team_task_performance` (line 166): `"active_status": "On Shift" if s.is_active else "Off Duty"`
- **Impact:** An employee account can be active (`is_active = True`) but currently off-duty (`on_shift = False`), or vice versa. Treating account activation as shift status produces incorrect clinic roster reports and contradicts the multi-factor staff status rules established in Phase 2.
- **Recommended Fix:** Decouple `s.is_active` (account status) from `getattr(s, "on_shift", True)` (shift availability) in all analytics, roster calculations, and summaries.

---

### Finding 2: Unsafe Role Fallback Defaulting to Clinic Owner
- **Severity:** MEDIUM
- **Affected File:** `apps/practicare/backend/ai/tools.py`
- **Relevant Function:** `execute_get_team_task_performance` (lines 156–180)
- **Impact:** The `if/elif/else` role ladder specifically checks `CLINICAL_AUDITOR`, `NURSE_STAFF`, and `ATTENDING_PHYSICIAN`. Any unhandled or unknown role fell through to `else:`, which exposed the full transparent `CLINIC_OWNER / Admin` workload and analytics.
- **Recommended Fix:** Change fallback to deny or raise authorization error by default, and only grant executive transparency to explicitly verified `CLINIC_OWNER` or system administrator roles.

---

### Finding 3: Monolithic `tools.py` and Lack of Domain Separation (SRP Violation)
- **Severity:** MEDIUM
- **Affected File:** `apps/practicare/backend/ai/tools.py` (915 lines)
- **Impact:** All 11 handlers for completely distinct business domains (tasks, checklists, rooms, staff, inventory, facility summaries) are lumped into one massive script. Changes to inventory logic risk breaking task scheduling.
- **Recommended Fix:** Decompose `ai/tools.py` into cohesive domain modules under `apps/practicare/backend/ai/handlers/`:
  - `tasks.py` (`execute_list_tasks`, `execute_create_clinical_task`, `execute_update_task_status`)
  - `checklists.py` (`execute_update_checklist_status`, `execute_delete_clinical_checklist`)
  - `staff.py` (`execute_search_staff`)
  - `rooms.py` (`execute_search_rooms`, `execute_get_room_turnover_status`)
  - `inventory.py` (`execute_get_inventory_status`)
  - `analytics.py` (`execute_get_team_task_performance`, `execute_get_practice_summary`)
  - Re-export all handlers from `ai/tools.py` to maintain 100% backward compatibility for all registry callers.

---

### Finding 4: Duplicated Task ID Normalization & Entity Resolution Logic (DRY Violation)
- **Severity:** MEDIUM
- **Affected File:** `apps/practicare/backend/ai/tools.py`
- **Relevant Functions:** `execute_list_tasks` (lines 570–579) and `execute_update_task_status` (lines 676–686)
- **Impact:** Duplicate logic generates candidate ID lists (`tsk-X`, `task-X`, `tsk-0X`) using different ad-hoc strategies.
- **Recommended Fix:** Extract a shared helper `normalize_task_id_candidates(raw_id: str) -> List[str]` in `ai/helpers.py`.

---

### Finding 5: Unsupported / Dead Schema Arguments in Tool Metadata
- **Severity:** MEDIUM
- **Affected File:** `apps/practicare/backend/ai/metadata.py`
- **Relevant Schemas:**
  - `SearchStaffArgs.department`: `models.Staff` has no `department` column (`id, name, role, is_active, on_shift, user_id, practice_id, tenant_id`).
  - `GetInventoryStatusArgs.category`: `models.InventoryItem` has no `category` column (`id, item_name, current_stock, min_threshold, unit, expiry_date, room_id, practice_id, tenant_id`).
- **Impact:** Gemini may attempt to filter by department or category, but the handlers silently ignore the arguments because the database schema lacks corresponding columns.
- **Recommended Fix:** Keep fields optional in schemas for backwards compatibility, but document in docstrings and handle safely without phantom SQL filters.

---

### Finding 6: Fabricated Compliance Score Metric
- **Severity:** MEDIUM
- **Affected File:** `apps/practicare/backend/ai/tools.py`
- **Relevant Function:** `execute_get_team_task_performance` (line 69)
- **Impact:** For `CLINICAL_AUDITOR`, `"compliance_score": "98.4% (Pass)" if overdue_ratio < 15 else "Review Recommended"`. The literal `"98.4%"` is a hardcoded metric rather than a calculated metric derived from actual tenant tasks (`round(100.0 - overdue_ratio, 1)`).
- **Recommended Fix:** Compute actual compliance score dynamically: `f"{round(max(0.0, 100.0 - overdue_ratio), 1)}% (Pass)" if overdue_ratio < 15 else "Review Recommended"`.

---

### Finding 7: Missing `INVENTORY_MANAGER` Role Permissions in `context.py`
- **Severity:** MEDIUM
- **Affected File:** `apps/practicare/backend/ai/context.py`
- **Relevant Mapping:** `ROLE_PERMISSIONS` dictionary
- **Impact:** `INVENTORY_MANAGER` is a valid role recognized throughout PractiCare models, but is missing from `ROLE_PERMISSIONS`. If an Inventory Manager invokes the AI agent, they are treated as an empty-permission role.
- **Recommended Fix:** Add `"INVENTORY_MANAGER": ["inventory:read", "inventory:write", "rooms:read"]` to `ROLE_PERMISSIONS`.

---

### Finding 8: Excessive Monolith Size in `ai/agent.py` (SRP Violation)
- **Severity:** LOW
- **Affected File:** `apps/practicare/backend/ai/agent.py` (1659 lines)
- **Impact:** Single file contains LangGraph graph assembly, Gemini client lifecycle, transient error retry loops, executive privacy filtering, four graph node implementations, and 800+ lines of deterministic report formatting.
- **Recommended Fix:** Keep public `PractiCareLangGraphAgent` and `agent` instance intact, but cleanly organize internal logic into helper utilities (`ai/agent_prompts.py` or modular synthesis routines).

---

### Finding 9: Missing Transaction Rollback in Tool Handlers
- **Severity:** LOW
- **Affected File:** `apps/practicare/backend/ai/tools.py`
- **Relevant Functions:** `execute_create_clinical_task`, `execute_update_task_status`, `execute_update_checklist_status`, `execute_delete_clinical_checklist`
- **Impact:** If a database exception occurs mid-transaction, `db.rollback()` was not explicitly called in a `try...except` block, leaving the SQLAlchemy session in a dirty/failed state.
- **Recommended Fix:** Enclose state mutations in `try...except` blocks with explicit `db.rollback()` before re-raising.

---

### Finding 10: Inconsistent String-to-Boolean Evaluation
- **Severity:** LOW
- **Affected File:** `apps/practicare/backend/ai/tools.py`
- **Relevant Functions:** `execute_list_tasks`, `execute_get_inventory_status`
- **Impact:** Using standard Python `bool(val)` on string values like `"false"` evaluates to `True`.
- **Recommended Fix:** Use a safe boolean conversion utility: `parse_bool_arg(val) -> bool` that handles strings `"true"`, `"false"`, `"0"`, `"1"`, `True`, `False`.

---

### Finding 11: Unused Imports in AI Modules
- **Severity:** LOW
- **Affected Files:** `apps/practicare/backend/ai/agent.py`, `apps/practicare/backend/ai/tools.py`
- **Impact:** Minor code cleanliness issue.
- **Recommended Fix:** Remove unused imports during code cleanup.

---

## 5. Security & Isolation Verification

| Boundary | Mechanism | Verification Status |
|:---|:---|:---|
| **Tenant Isolation** | All SQL queries filtered by `tenant_id == context.tenant_id`. Gateway injects authenticated tenant ID and strips client-provided tenant spoofing. | Verified via `test_ai_privacy_and_tools.ps1` & `test_practicare_ai.ps1`. |
| **Conversation Privacy** | `AIConversation` records filtered strictly by `(tenant_id, user_id, conversation_id)`. Cross-user access returns HTTP 404. | Verified via `test_ai_privacy_and_tools.ps1`. |
| **Role-Based Access Control** | `ToolGateway` checks required permissions against `ROLE_PERMISSIONS[context.user_role]` before tool execution. | Verified (Nurse blocked from salary query and checklist deletion). |
| **Executive Data Protection** | `validate_sensitive_query` intercepts queries containing executive salary, compensation, or private evaluations before tool planning. | Verified via Scenario 3 in `test_practicare_ai.ps1`. |
| **Human-In-The-Loop Approval** | Destructive actions (`delete_clinical_checklist`) intercepted with high-risk approval token; executed only after explicit `/api/v1/ai/approve` confirmation. | Verified via Scenarios 6–8 in `test_practicare_ai.ps1`. |

---

## 6. Proposed Architecture & Refactoring Plan

### Target Structure

```
apps/practicare/backend/ai/
├── __init__.py           # Public exports (SecurityContext, ToolGateway, agent, registry, etc.)
├── context.py            # SecurityContext & ROLE_PERMISSIONS (updated with INVENTORY_MANAGER)
├── metadata.py           # ToolMetadata, ToolRiskLevel, argument Pydantic schemas
├── approvals.py          # ApprovalManager, PendingApproval
├── registry.py           # ToolRegistry (registers domain handlers)
├── gateway.py            # ToolGateway (zero-trust execution, RBAC, tenant protection, audit)
├── helpers.py            # Shared utility functions (task ID normalization, safe boolean parsing, entity queries)
├── handlers/             # Domain-specific tool handlers (Decomposed from monolithic tools.py)
│   ├── __init__.py       # Exports all 11 handlers
│   ├── tasks.py          # execute_list_tasks, execute_create_clinical_task, execute_update_task_status
│   ├── checklists.py     # execute_update_checklist_status, execute_delete_clinical_checklist
│   ├── staff.py          # execute_search_staff
│   ├── rooms.py          # execute_search_rooms, execute_get_room_turnover_status
│   ├── inventory.py      # execute_get_inventory_status
│   └── analytics.py      # execute_get_team_task_performance, execute_get_practice_summary
├── tools.py              # Backward-compatibility facade (re-exports all handlers from handlers/)
└── agent.py              # LangGraph orchestration with clean modular synthesis helpers
```

### Refactoring Strategy & Safety Rules
1. **Incremental Execution:** Build domain handlers one by one under `apps/practicare/backend/ai/handlers/`.
2. **Backward-Compatibility Facade:** Keep `apps/practicare/backend/ai/tools.py` re-exporting every handler function with identical signature so existing imports in `registry.py` and tests continue working seamlessly.
3. **No Schema Changes:** Keep database models intact; fix code-level bugs (status confusion, unhandled roles, hardcoded scores, boolean parsing).
4. **Continuous Regression Testing:** Re-run PowerShell test suites after each incremental change.
