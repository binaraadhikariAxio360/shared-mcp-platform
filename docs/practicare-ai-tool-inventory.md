# PractiCare AI Tool Gateway & Registry Inventory

**Date:** October 14, 2026  
**Auditor:** Senior AI Agent Engineer & Security Architect  
**Architecture:** Centralized Tool Registry (`ai.registry`), Tool Gateway (`ai.gateway`), Domain Handlers (`ai.handlers/`)

---

## Overview

The PractiCare AI subsystem registers 11 operational clinical tools in `ai.registry.registry`. Every tool is executed strictly through `ToolGateway.execute(tool_name, args, context, db)`.

### Security Invariants:
1. **Dynamic Schema Filtering:** `ToolRegistry.get_schemas_for_role(role)` exposes only the tools permitted for the caller's verified role to the Gemini model or LangGraph planner.
2. **Gateway Authorization Enforcement:** Even if a tool call is injected or synthesized by the LLM, `ToolGateway.execute()` verifies `context.has_permission(p)` and `tool.allowed_roles` before invoking the handler.
3. **Strict Tenant Scoping:** Every handler enforces `models.Entity.tenant_id == context.tenant_id`.
4. **Post-Write PostgreSQL Verification:** Every mutation tool performs a database commit and a fresh read within the tenant before returning `SUCCESS`.

---

## Complete Tool Inventory Matrix

| # | Tool Name | Read/Write | Risk Level | Required Permissions | Allowed Roles | Approval Required | Handler Function |
| :-: | :--- | :---: | :---: | :--- | :--- | :---: | :--- |
| **1** | `get_team_task_performance` | Read-Only | LOW | `tasks:view_all`, `tasks:view_department`, `tasks:view_operational`, `tasks:view_audit` | CLINIC_OWNER, ATTENDING_PHYSICIAN, CLINICAL_AUDITOR, NURSE_STAFF | No | `ai.handlers.analytics::execute_get_team_task_performance` |
| **2** | `get_room_turnover_status` | Read-Only | LOW | `rooms:view` | CLINIC_OWNER, ATTENDING_PHYSICIAN, NURSE_STAFF | No | `ai.handlers.rooms::execute_get_room_turnover_status` |
| **3** | `search_rooms` | Read-Only | LOW | `rooms:view` | CLINIC_OWNER, ATTENDING_PHYSICIAN, NURSE_STAFF, INVENTORY_MANAGER | No | `ai.handlers.rooms::execute_search_rooms` |
| **4** | `search_staff` | Read-Only | LOW | `staff:view` | CLINIC_OWNER, ATTENDING_PHYSICIAN, NURSE_STAFF, INVENTORY_MANAGER, CLINICAL_AUDITOR | No | `ai.handlers.staff::execute_search_staff` |
| **5** | `list_tasks` | Read-Only | LOW | `tasks:view` | CLINIC_OWNER, ATTENDING_PHYSICIAN, NURSE_STAFF, CLINICAL_AUDITOR | No | `ai.handlers.tasks::execute_list_tasks` |
| **6** | `create_clinical_task` | Read/Write | MEDIUM | `tasks:create` | CLINIC_OWNER, ATTENDING_PHYSICIAN | No | `ai.handlers.tasks::execute_create_clinical_task` |
| **7** | `update_task_status` | Read/Write | MEDIUM | `tasks:update` | CLINIC_OWNER, ATTENDING_PHYSICIAN, NURSE_STAFF | No | `ai.handlers.tasks::execute_update_task_status` |
| **8** | `get_inventory_status` | Read-Only | LOW | `inventory:view` | CLINIC_OWNER, ATTENDING_PHYSICIAN, INVENTORY_MANAGER, NURSE_STAFF | No | `ai.handlers.inventory::execute_get_inventory_status` |
| **9** | `get_practice_summary` | Read-Only | LOW | `practice:view_summary` | CLINIC_OWNER, ATTENDING_PHYSICIAN, CLINICAL_AUDITOR, NURSE_STAFF | No | `ai.handlers.analytics::execute_get_practice_summary` |
| **10** | `update_checklist_status` | Read/Write | MEDIUM | `checklists:update` | CLINIC_OWNER, ATTENDING_PHYSICIAN, NURSE_STAFF | No | `ai.handlers.checklists::execute_update_checklist_status` |
| **11** | `delete_clinical_checklist` | Destructive | HIGH | `checklists:delete` | CLINIC_OWNER | **YES (HITL)** | `ai.handlers.checklists::execute_delete_clinical_checklist` |

---

## Detailed Tool Specifications

### 1. `get_team_task_performance`
- **Purpose:** Analyzes clinical task completion rates, overdue tasks, pending bottlenecks, and operational workloads for the clinic.
- **Input Schema:** `EmptyArgs` (`{}`)
- **Output Schema:** `{ "tenant_id": str, "total_tasks": int, "completed": int, "pending": int, "overdue": int, "completion_rate": float, "workload_by_provider": [...] }`
- **Scoping Behavior:** Scoped by role. CLINICAL_AUDITOR receives anonymized provider identifiers (e.g., `Staff Member A`). ATTENDING_PHYSICIAN receives clinical procedures. CLINIC_OWNER receives full provider workload tables.

### 2. `get_room_turnover_status`
- **Purpose:** Live exam/surgery room statuses (Available, Occupied, Turnover).
- **Input Schema:** `EmptyArgs` (`{}`)
- **Output Schema:** `{ "tenant_id": str, "total_rooms": int, "occupancy": { "Available": int, "Occupied": int, "Turnover": int }, "rooms": [...] }`

### 3. `search_rooms`
- **Purpose:** Resolves natural language room references (e.g. "101", "Room 101", "Primary Exam") to database `room_id` (e.g. `room-101`).
- **Input Schema:** `SearchRoomsArgs` (`{ "query": str, "limit": int }`)
- **Output Schema:** `{ "tenant_id": str, "query": str, "match_count": int, "rooms": [{ "room_id": str, "room_number": str, "name": str, "status": str, "display_label": str }] }`
- **Error Recovery:** If `match_count == 0`, agent halts and prompts user to select a valid room. If `match_count > 1`, agent halts and prompts user for clarification.

### 4. `search_staff`
- **Purpose:** Resolves clinical staff names (e.g. "Dr. Sarah", "Marcus", "stf-02") to database `staff_id`.
- **Input Schema:** `SearchStaffArgs` (`{ "query": str, "limit": int }`)
- **Output Schema:** `{ "tenant_id": str, "query": str, "match_count": int, "staff": [{ "staff_id": str, "name": str, "role": str, "is_active": bool, "on_shift": bool, "display_label": str }] }`
- **Validation:** Filters strictly by `tenant_id`. Flags inactive staff members to prevent assigning tasks to deactivated accounts.

### 5. `list_tasks`
- **Purpose:** Retrieves clinical tasks with multi-parameter filtering (status, priority, assigned_staff_id, room_id, overdue_only).
- **Input Schema:** `ListTasksArgs` (`{ "task_id": Optional[str], "status": Optional[str], "priority": Optional[str], "assigned_staff_id": Optional[str], "room_id": Optional[str], "overdue_only": bool, "limit": int }`)
- **Output Schema:** `{ "tenant_id": str, "total_returned": int, "pending_count": int, "overdue_count": int, "tasks": [...] }`

### 6. `create_clinical_task`
- **Purpose:** Creates a new clinical task for a specific room and assigned staff member.
- **Input Schema:** `CreateClinicalTaskArgs` (`{ "title": str, "room_id": str, "assigned_staff_id": Optional[str], "priority": str, "due_date": str, "description": Optional[str] }`)
- **Output Schema:** `{ "status": "SUCCESS", "task_id": str, "title": str, "priority": str, "due_date": str, "room_id": str, "assigned_staff_id": str, "tenant_id": str, "persisted": True }`
- **Database Write & Verification:** Commits to `tasks` table. Reads record back via SQLAlchemy query. If missing, rolls back and raises `RuntimeError`.

### 7. `update_task_status`
- **Purpose:** Updates status ('Pending', 'In Progress', 'Completed'), priority, or reassigns provider for an existing task.
- **Input Schema:** `UpdateTaskStatusArgs` (`{ "task_id": str, "status": Optional[str], "priority": Optional[str], "assigned_staff_id": Optional[str], "description": Optional[str] }`)
- **Output Schema:** `{ "status": "SUCCESS", "task_id": str, "updated_status": str, "priority": str, "assigned_to": str, "persisted": True }`

### 8. `get_inventory_status`
- **Purpose:** Medical supply inventory levels, low-stock alerts, out-of-stock items, and expiration dates.
- **Input Schema:** `GetInventoryStatusArgs` (`{ "low_stock_only": bool, "expiring_within_days": int }`)
- **Output Schema:** `{ "tenant_id": str, "total_items": int, "low_stock_count": int, "expiring_count": int, "items": [...] }`

### 9. `get_practice_summary`
- **Purpose:** High-level operational overview: facility rooms, task completion rate, on-shift staff counts, and inventory alerts.
- **Input Schema:** `GetPracticeSummaryArgs` (`{}`)
- **Output Schema:** `{ "tenant_id": str, "practice_name": str, "total_rooms": int, "active_staff": int, "on_shift_staff": int, "pending_tasks": int, "low_stock_items": int }`

### 10. `update_checklist_status`
- **Purpose:** Updates or toggles completion status for sterilization/hygiene checklists.
- **Input Schema:** `UpdateChecklistStatusArgs` (`{ "checklist_id": str, "is_completed": bool }`)
- **Output Schema:** `{ "status": "SUCCESS", "checklist_id": str, "title": str, "is_completed": bool, "persisted": True }`

### 11. `delete_clinical_checklist`
- **Purpose:** Permanently deletes a checklist record from the database.
- **Classification:** HIGH RISK (Destructive).
- **Enforcement:** Requires human-in-the-loop approval. First call returns `approval_required` with an approval token. Second call with valid `approval_id` executes the deletion.
