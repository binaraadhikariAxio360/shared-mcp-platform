# PractiCare AI Stabilization & Role Hierarchy Report

**Project**: PractiCare Clinical Operations AI Assistant  
**Target Systems**: `apps/practicare/backend`, `apps/practicare/frontend`, `tests`  
**Date**: October 2026  
**Status**: **Stabilization Complete — All Tests Passing (43/43)**

---

## 1. Executive Summary

This report documents the stabilization and business-specific role hierarchy implementation for PractiCare. The development team stabilized the FastAPI backend, LangGraph clinical operations agent, Tool Gateway pipeline, PostgreSQL schema, and Next.js frontend to strictly enforce the confirmed role hierarchy:

$$\textbf{OWNER} > \textbf{MANAGER} > \textbf{DOCTOR} > \textbf{NURSE}$$

All fake AI responses, hardcoded stub messages, and false success confirmations have been eliminated. Every AI interaction now invokes verified database execution handlers through the Tool Gateway, asserting schema validation, tenant boundary checks, role authorization, persistent approvals, and audit logging.

---

## 2. Confirmed Role Permission Matrix

| Resource & Operation | Tool / Endpoint | OWNER | MANAGER | DOCTOR | NURSE |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Tasks: View List** | `list_clinical_tasks` | ✅ Company-wide | ✅ Company-wide | ✅ Doctor/Nurse Scope | ✅ Self-Assigned Only |
| **Tasks: View Details** | `get_task_details` | ✅ Full Details | ✅ Full Details | ✅ Scope Only | ✅ Self-Assigned Only |
| **Tasks: Create** | `create_clinical_task` | ✅ Yes | ✅ Assign to Staff | ✅ Assign to Nurses | ❌ Forbidden |
| **Tasks: Update Details** | `update_task_details` | ✅ Full Details | ✅ Full Details | ✅ Scope Only | ❌ Forbidden |
| **Tasks: Complete** | `update_task_status` | ✅ Any Task | ✅ Any Task | ✅ Own & Nurse Tasks | ✅ Self-Assigned Only |
| **Tasks: Delete** | `delete_clinical_task` | ✅ Any Task | ✅ Except Self-Assigned | ✅ Except Self-Assigned | ❌ Forbidden |
| **Checklists: View** | `list_checklists` | ✅ All | ✅ All | ✅ All | ✅ All Company Checklists |
| **Checklists: View Details**| `get_checklist_details` | ✅ Full Details | ✅ Full Details | ✅ Full Details | ✅ All Company Checklists |
| **Checklists: Create** | `create_clinical_checklist` | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Forbidden |
| **Checklists: Edit Def** | `update_clinical_checklist`| ✅ Yes | ✅ Yes | ✅ Yes | ❌ Forbidden |
| **Checklists: Toggle Done** | `update_checklist_status` | ✅ Any | ✅ Any | ✅ Any | ✅ Self-Assigned Only |
| **Checklists: Delete** | `delete_clinical_checklist`| ✅ Yes | ✅ Yes | ✅ Yes | ❌ Forbidden |
| **Inventory: View** | `get_inventory_status` | ✅ Yes | ✅ Yes | ✅ Read-only | ✅ Read-only / AI Summary |
| **Inventory: Manage** | `update_inventory_stock` | ✅ Yes | ✅ Yes | ❌ Forbidden | ❌ Forbidden |
| **Rooms: Add** | `create_clinic_room` | ✅ Yes | ✅ Yes | ❌ Forbidden | ❌ Forbidden |
| **Rooms: Change Status** | `update_room_turnover` | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Forbidden (Read-only) |

---

## 3. Implemented vs Missing Functionality

### Implemented Functionality
1. **Centralized Backend Authorization Engine (`ai/policy.py`)**:
   - Built a single source of truth for authorization checks across REST API and AI Agent.
   - Handles role hierarchy aliases (`CLINIC_OWNER` / `OWNER`, `INVENTORY_MANAGER` / `MANAGER`, `ATTENDING_PHYSICIAN` / `DOCTOR`, `NURSE_STAFF` / `NURSE`).
   - Lineage tracking ensures Doctors cannot read, edit, or delete Owner/Manager records.
2. **Tool Gateway 6-Step Verification (`ai/gateway.py`)**:
   - Enforces Step 1 schema validation, Step 2 tenant isolation, Step 3 policy validation, Step 4 approval gating, Step 5 real DB execution, and Step 6 tamper-evident audit logging.
3. **Removal of Hallucinated AI Responses (`ai/agent.py`)**:
   - Replaced canned fallback responses with verified tool execution synthesis.
   - Refined intent detection word boundaries (`\b(?:assign|reassign)\b`) and toggle priorities (`\b(?:tick|untick|toggle|complete)\b`) to prevent false assignment warnings on identifiers like `check-assigned-inv`.
   - Markdown generation confirms actual database mutations with record details.
4. **Task & Checklist Lineage (`models.py`)**:
   - Added nullable `created_by_user_id` and `created_by_role` columns to `Task` and `Checklist` models.
5. **Frontend Role Alignment (`frontend/src/app/page.tsx`)**:
   - Dynamic permission flags: `canCreateTask`, `canEditTask`, `canDeleteTaskItem`, `canToggleTaskItem`, `canCreateChecklist`, `canEditChecklist`, `canDeleteChecklist`, `canToggleChecklistItem`, `canManageInventory`, `canAddRoom`, `canUpdateRoomStatus`.
   - Disabled unauthorized controls and added contextual tooltips.
   - Filtered Doctor task assignment candidate options exclusively to Nurses.
6. **Non-Destructive PostgreSQL Migration (`migrations/002_role_hierarchy_lineage.sql`)**:
   - Creates required lineage columns and indexes without breaking existing PostgreSQL data.

### Missing / Deferred Functionality
- **MCP Server & MCP Client**: Explicitly deferred per instructions (`DO NOT IMPLEMENT MCP SERVER OR MCP CLIENT IN THIS PHASE`).

---

## 4. Modified Files Log

| File | Purpose |
| :--- | :--- |
| `apps/practicare/backend/ai/policy.py` | Centralized authorization policy for the role hierarchy. |
| `apps/practicare/backend/models.py` | Lineage tracking columns for Tasks and Checklists. |
| `apps/practicare/backend/ai/context.py` | Role permissions and allowed tools dictionary. |
| `apps/practicare/backend/ai/registry.py` | Tool schemas and role access lists for all 14 clinical tools. |
| `apps/practicare/backend/ai/gateway.py` | Gateway Step 3 policy validation hook. |
| `apps/practicare/backend/ai/agent.py` | LLM prompt and deterministic intent matcher alignment. |
| `apps/practicare/backend/ai/handlers/tasks.py` | Lineage setting, scope filtering, and authorization enforcement. |
| `apps/practicare/backend/ai/handlers/checklists.py` | Company-wide visibility + self-assigned mutation restrictions. |
| `apps/practicare/backend/ai/handlers/operations.py` | Room creation and checklist creation policy checks. |
| `apps/practicare/backend/ai/handlers/inventory.py` | Normalized status envelope for inventory query tool. |
| `apps/practicare/backend/main.py` | Endpoints enforce `ai.policy`; imported `approval_manager`. |
| `apps/practicare/backend/migrations/002_role_hierarchy_lineage.sql` | PostgreSQL schema migration for lineage columns. |
| `apps/practicare/frontend/src/app/page.tsx` | Frontend UI controls, profiles, and permission hooks alignment. |
| `tests/test_stabilization_permissions.py` | 30 unit and integration tests for role hierarchy and AI parity. |

---

## 5. Test Pass / Fail Results

### Summary: 43 Tests Run — 43 Passed (100% Pass Rate)

| Test Suite | Tests | Result | Status |
| :--- | :---: | :---: | :---: |
| `tests/test_stabilization_permissions.py` | 30 | 30 Passed | ✅ OK |
| `tests/test_verified_execution_and_rbac.py` | 3 | 3 Passed | ✅ OK |
| `tests/test_practicare_crud.py` | 4 | 4 Passed | ✅ OK |
| `apps/practicare/backend/test_phase0_security.py` | 6 | 6 Passed | ✅ OK |
| **Combined Total** | **43** | **43 Passed** | **100% Passing** |

### Key Scenarios Verified by Tests
- **Owner Scope**: Full CRUD across all entities; blocked from accessing other tenants.
- **Manager Scope**: Full inventory CRUD; add rooms; change room status; create/edit/delete tasks and checklists; assigning work to staff; **blocked from deleting self-assigned tasks**.
- **Doctor Scope**: Create/edit/delete tasks and checklists in scope; assign tasks to Nurses; complete own and Nurse tasks; **blocked from deleting self-assigned tasks**; **blocked from modifying or retrieving Owner/Manager tasks**; **blocked from adding rooms**; **blocked from managing inventory**.
- **Nurse Scope**: Complete own assigned tasks; view all company checklists; tick/untick only self-assigned checklists; **blocked from creating/editing/deleting tasks**; **blocked from completing other users' tasks**; **blocked from modifying other users' checklists**; **blocked from editing checklist definitions**; **read-only inventory & rooms**; **blocked from changing room status**.
- **AI Agent Parity**: Verified that natural language prompts execute the exact equivalent operations as manual REST endpoints without false success confirmations.

---

## 6. Manual vs AI Parity Status

Every authorized manual action has an equivalent, verified AI natural language workflow:

| Domain | Manual Flow | AI Prompt | Verification Status |
| :--- | :--- | :--- | :---: |
| **Task Performance** | Dashboard & Tasks board | "I want to know how my team is performing the tasks" | ✅ Verified |
| **Checklist Tick** | Checklist toggle checkbox | "Mark checklist check-assigned-nurse as complete" | ✅ Verified |
| **Task Complete** | Task row checkbox | "Mark task task-assigned-nurse as completed" | ✅ Verified |
| **Inventory Status** | Inventory tab live table | "Which medical supplies or inventory items are running low?" | ✅ Verified |
| **Room Turnover** | Room status action button | "Update room room-a to Turnover" | ✅ Verified |
| **Task Creation** | Add Task modal dialog | "Create clinical task: Sanitize Bay 1" | ✅ Verified |
| **Checklist Creation**| Add Checklist modal dialog | "Create clinical checklist: End of Day Sterilization" | ✅ Verified |

---

## 7. Tenant Isolation & Lineage Verification

- **Tenant Isolation**: Confirmed that `tenant-001` (Apex Health) and `tenant-002` (Metro Health) cannot access or modify each other's records through REST endpoints or AI tools.
- **Lineage Protection**: Tasks and checklists created by Owner or Manager are tagged with `created_by_role`. Doctors and Nurses attempting to query or mutate them via AI receive access denied blocks.
- **Identity Integrity**: User identity, tenant ID, and role are verified from signed JWT tokens, mitigating header-spoofing attacks.

---

## 8. Remaining Blockers & Demo Readiness

- **Blockers**: None. System is stable and free of runtime regressions.
- **Demo Readiness**: **100% READY FOR LIVE DEMONSTRATION**.
