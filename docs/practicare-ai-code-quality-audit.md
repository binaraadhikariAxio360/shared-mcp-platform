# PractiCare AI Code Quality, Design & Architecture Audit

**Date:** October 14, 2026  
**Auditor:** Principal Software Architect & QA Automation Engineer  
**Frameworks Evaluated:** SOLID, DRY, KISS, YAGNI, Separation of Concerns, Least Privilege, Clean Architecture

---

## 1. Architectural Overview & Component Structure

The PractiCare backend is organized under `apps/practicare/backend/`:
```
apps/practicare/backend/
├── main.py                 # FastAPI application, route handlers, middleware & security dependencies
├── models.py               # SQLAlchemy ORM declarative models (PostgreSQL 16)
├── schemas.py              # Pydantic v2 validation models & request/response contracts
├── security.py             # HMAC-SHA256 session token generation and verification
├── database.py             # Engine initialization, session management & idempotent migrations
└── ai/
    ├── agent.py            # LangGraph StateGraph orchestrator & node logic
    ├── gateway.py          # Zero-trust ToolGateway authorization & execution firewall
    ├── registry.py         # Centralized ToolRegistry (single source of truth for tool schemas)
    ├── metadata.py         # Pydantic tool argument schemas & risk classification
    ├── context.py          # Verified SecurityContext & role-based permission calculator
    ├── approvals.py        # Human-in-the-Loop (HITL) approval token manager
    ├── helpers.py          # Clinical entity normalizers, date utilities & candidate generators
    ├── tools.py            # Backward-compatibility facade re-exporting domain handlers
    └── handlers/           # Domain-driven tool implementation modules
        ├── tasks.py        # list_tasks, create_clinical_task, update_task_status
        ├── checklists.py   # update_checklist_status, delete_clinical_checklist
        ├── staff.py        # search_staff
        ├── rooms.py        # search_rooms, get_room_turnover_status
        ├── inventory.py    # get_inventory_status
        └── analytics.py    # get_team_task_performance, get_practice_summary
```

---

## 2. Code Quality & Architectural Principles Evaluation

### 2.1 Single Responsibility Principle (SRP)
- **Status:** **SATISFIED**
- **Evidence:** Tool execution was decomposed from monolithic script files into dedicated domain handler modules under `ai/handlers/`. Each module (`tasks.py`, `checklists.py`, `rooms.py`, `staff.py`, `inventory.py`, `analytics.py`) handles only its domain's database operations.
- `ai/registry.py` is solely responsible for tool metadata registration and role-based schema filtering.
- `ai/gateway.py` is solely responsible for permission checking, audit logging, and dispatching.
- `ai/approvals.py` manages tokenized HITL confirmations with automatic TTL expiration.

### 2.2 Don't Repeat Yourself (DRY)
- **Status:** **IMPROVED / SATISFIED**
- **Evidence:**
  - Common task ID normalization, overdue date checks, and staff active status calculations are consolidated into `ai.helpers`.
  - Permission sets are calculated centrally in `ai.context.SecurityContext.create()`.
  - Tool handlers re-use common entity lookups rather than duplicating queries.

### 2.3 Least Privilege & Zero Trust
- **Status:** **STRICTLY ENFORCED**
- **Evidence:**
  - Dynamic Tool Schema Filtering: `ToolRegistry.get_schemas_for_role(role)` hides unauthorized tools from Gemini prompt and LangGraph planner.
  - Gateway Enforcement: `ToolGateway.execute()` verifies `context.has_permission(p)` and `tool.allowed_roles` prior to invoking handlers.
  - Anonymized Scoping: `CLINICAL_AUDITOR` queries automatically strip employee PII and return aggregated data.
  - Tenant Scoping: Every single SQL query includes `WHERE tenant_id = context.tenant_id`.

### 2.4 False-Success Prevention (Integrity Invariant)
- **Status:** **RESOLVED & VERIFIED**
- **Root Cause Identified:** Previously, when a user entered a shorthand task creation command (such as `Post-op Sterilization & Restock,102,2026-10-15,High,Marcus`), `result_analysis_node` checked a hardcoded keyword list (`["assign", "reassign", "create", "task", "schedule"]`) which did not match shorthand messages. This caused `more_tools_needed` to be set to `False`, aborting the graph before `create_clinical_task` was executed. Gemini then synthesized an ungrounded natural-language reply claiming the task was created without an actual database write.
- **Fix Implemented:**
  1. `result_analysis_node` now evaluates zero matches and ambiguities first, halting immediately if an entity was not found or was ambiguous.
  2. `wants_action` now leverages `_is_task_creation_request(message)`, which reliably detects clinical keywords and shorthand comma-separated task parameters.
  3. `_has_verified_task_creation()` and `_claims_task_creation()` intercept any hallucinated creation claims and replace them with truthful error messages if PostgreSQL persistence is not verified.

---

## 3. Findings & Recommendations Matrix

| ID | Domain | Severity | Finding | Resolution / Recommendation |
| :---: | :--- | :---: | :--- | :--- |
| **F-01** | AI Graph Orchestration | **HIGH** | `result_analysis_node` keyword check failed on comma-separated shorthand inputs. | **RESOLVED:** Unified with `_is_task_creation_request(message)`. Verified with automated end-to-end tests. |
| **F-02** | Entity Resolution Order | **MEDIUM** | In multi-tool iterations, staff search failures were bypassed if room search matched first. | **RESOLVED:** Check zero matches for both rooms and staff before transitioning to write actions. |
| **F-03** | Legacy Tool Facade | **LOW** | `ai/tools.py` maintained for backward compatibility. | **RESOLVED:** `ai/tools.py` functions as a clean re-export facade to avoid breaking legacy tests. |
| **F-04** | Client Agent Mode Override | **LOW** | `agent_mode` in chat payload allowed overriding mode in dev. | **RESOLVED:** Restricted to `ENVIRONMENT=development` or `ENVIRONMENT=test`. Ignored in production. |
