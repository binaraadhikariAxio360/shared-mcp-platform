# CLAUDE.md - Shared MCP MOC Guidelines & Architecture

## Permanent Development Rules
1. **Session Start**: Always read `CLAUDE.md` and `PROJECT_STATUS.md`, then run `git status` before writing code.
2. **Session Update**: After every meaningful completed task, update `PROJECT_STATUS.md` with: changes made, tests performed/results, and next step.
3. **Verification Standard**: Never claim unverified work is complete. Always verify via automated tests or explicit checks.
4. **Security & Boundaries**: Never expose secrets (API keys, session tokens, passwords). Never modify unrelated apps without explicit instruction.
5. **Scope Guard**: Keep database changes backward-compatible and non-destructive. Preserve existing test pass rates.

---

## Project Overview & 4 MOC Apps
The repository hosts 4 vertical domain applications (MOC - Model of Concept) backed by a shared PostgreSQL database (`moc-postgres-db`, port 5433 host / 5432 container) and a shared platform layer:

| Application | Domain | Frontend | Backend | Status |
| :--- | :--- | :--- | :--- | :--- |
| **PractiCare** (`apps/practicare`) | Clinical operations, tasks, checklists, inventory, rooms | Port 3001 (Next.js) | Port 5001 (FastAPI) | Fully stabilized & verified |
| **TaxSnap** (`apps/taxsnap`) | Receipt scanning, tax deduction & financial categorization | Port 3002 (Next.js) | Port 5002 (FastAPI) | Scaffolding complete; AI pending MCP |
| **PropSights** (`apps/propsights`) | Property management, lease tracking, real estate analytics | Port 3003 (Next.js) | Port 5003 (FastAPI) | Scaffolding complete; AI pending MCP |
| **OnScribe** (`apps/onscribe`) | Medical dictation, clinical notes, transcript processing | Port 3004 (Next.js) | Port 5004 (FastAPI) | Scaffolding complete; AI pending MCP |

---

## PractiCare AI Architecture

### 1. PractiCare AI Agent (`apps/practicare/backend/ai/agent.py`)
- **Engine**: Gemini 3.1 Flash-Lite orchestrated via a LangGraph `StateGraph`.
- **Pipeline**: `agent_reasoning` -> `tool_execution` -> `result_analysis` -> `response_synthesis`.
- **Intent-Aware Routing**: Classifies prompts into `action`, `retrieval`, `explanation`, `concise_analysis`, `detailed_analysis`, or `report`.
- **Dynamic Resolution**: Automatically resolves staff names (e.g., "John" -> `stf-05`), room labels ("Room 101" -> `room-101`), relative dates ("tomorrow"), and normalized task IDs (`tsk-15`).
- **Human-in-the-Loop Approvals (`ai/approvals.py`)**: Intercepts high-impact operations (e.g., task/checklist deletion) and issues cryptographic approval tokens (`appr-*`).

### 2. Tool Registry (`apps/practicare/backend/ai/registry.py`)
- Catalogs 14 clinical tools with strict Pydantic schemas, descriptions, and role permissions:
  - Task Operations: `list_clinical_tasks`, `get_task_details`, `create_clinical_task`, `update_task_details`, `update_task_status`, `delete_clinical_task`
  - Checklist Operations: `list_checklists`, `get_checklist_details`, `create_clinical_checklist`, `update_clinical_checklist`, `update_checklist_status`, `delete_clinical_checklist`
  - Inventory & Rooms: `get_inventory_status`, `update_inventory_stock`, `create_clinic_room`, `update_room_turnover`

### 3. Tool Gateway 6-Step Verification (`apps/practicare/backend/ai/gateway.py`)
All tool invocations from the AI agent pass through mandatory gateway validation:
1. **Schema Validation**: Validates arguments against registered Pydantic schema.
2. **Tenant Boundary Assertion**: Enforces matching `tenant_id` between context and request payload.
3. **Role & Lineage Policy Validation**: Enforces centralized pure functions (`ai/policy.py`).
4. **Approval Flow Interception**: Suspends destructive actions until approved with valid signature.
5. **Execution & Real DB Persistence**: Executes handler in active SQLAlchemy session; rolls back on failure.
6. **Audit Event Logging**: Emits structured tamper-evident logs in `ai_audit_events`.

---

## Security Boundaries & Governance Model

### 1. Role Hierarchy (`apps/practicare/backend/ai/policy.py`)
$$\textbf{OWNER} > \textbf{MANAGER} > \textbf{DOCTOR} > \textbf{NURSE}$$
- **OWNER**: Full CRUD across tenant resources.
- **MANAGER**: Full inventory CRUD; manages tasks/checklists; prohibited from deleting self-assigned tasks.
- **DOCTOR**: Manages doctor/nurse scoped tasks; assigns tasks to nurses; cannot view/modify Owner/Manager tasks; cannot delete self-assigned tasks; read-only inventory.
- **NURSE**: Completes own tasks; views company checklists but ticks only self-assigned checklists; read-only inventory & rooms; cannot create/delete tasks.

### 2. Tenant & Lineage Isolation
- **Tenant Isolation**: Cryptographic tenant boundaries (`tenant-001` vs `tenant-002`) on all tables; cross-tenant access returns `403 Forbidden` or `404 Not Found`.
- **Lineage Tracking**: Tasks and checklists record `created_by_user_id` and `created_by_role`. Lower roles cannot view or mutate higher-role artifacts.
- **Authentication**: Stateless HMAC-SHA256 session tokens (`pcsess.*`). Authenticated requests ignore forged client headers.

---

## Planned Shared MCP Server Architecture
- **Location**: `platform/shared-mcp-server`, `platform/tool-registry`, `platform/ai-tool-gateway`, and `packages/mcp-client`.
- **Objective**: Expose tools from all 4 MOC applications through a unified Model Context Protocol (MCP) server.
- **Key Tenet**: The Shared MCP Server will delegate execution through the existing Tool Gateway pipeline, preserving tenant scoping, RBAC checks, approval flows, and audit logging across all 4 apps.

---

## Useful Commands
- **Run Core Permissions & Gateway Tests**:
  ```powershell
  pytest tests/test_stabilization_permissions.py tests/test_verified_execution_and_rbac.py tests/test_practicare_crud.py
  ```
- **Check Git Status**:
  ```powershell
  git status
  ```
- **Run Frontends Locally**:
  ```powershell
  npm run dev:practicare
  # or dev:all-frontends
  ```
