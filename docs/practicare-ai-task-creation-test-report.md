# PractiCare AI Task Creation & Hallucination Prevention Test Report

**Date:** October 14, 2026  
**Auditor:** Principal AI Agent Engineer & QA Automation Architect  
**Subsystem:** LangGraph Autonomous Clinical AI Agent (`ai/agent.py`, `ai/gateway.py`, `ai/handlers/tasks.py`)  
**Models Tested:** Google Gemini 3.1 Flash-Lite (Live API) & Deterministic Clinical Planner

---

## 1. Problem Investigation & Root Cause Analysis

### 1.1 Previous Observed Defect
- **User Input:** `Post-op Sterilization & Restock,102,2026-10-15,High,Kavi`
- **Observed Behavior:**
  - AI responded: "Task successfully created."
  - Execution trace showed only `search_rooms` and `search_staff`, NOT `create_clinical_task`.
  - Database check revealed NO task was written to PostgreSQL.
  - Subsequent `list_tasks` queries returned 0 tasks.

### 1.2 Confirmed Root Cause
1. **Keyword Filter Mismatch in Graph Routing:**
   In `ai/agent.py`'s `result_analysis_node`, the transition to subsequent iterations checked:
   `wants_assign = any(w in lower for w in ["assign", "reassign", "create", "task", "schedule"])`
   When users submitted clinical shorthand (e.g. `Post-op Sterilization & Restock,102,2026-10-15,High,Marcus`), none of those five specific words were present, even though the request was an explicit task creation request.
   As a result, `more_tools_needed` was evaluated as `False`, aborting the LangGraph loop before `create_clinical_task` could be dispatched.
2. **Ungrounded Synthesis in Report Node:**
   When the graph routed prematurely to `report_synthesis_node`, the LLM synthesized an ungrounded natural-language reply stating the task was created, even though no database tool had actually executed.
3. **Staff Resolution Gating for Non-Existent Providers:**
   In `tenant-001`, no staff member named `Kavi` existed. When `search_staff(query="Kavi")` executed, `match_count` was 0. However, because room search matched 1 room, the room check returned `more_tools_needed = True` before evaluating the staff search failure, leading to ambiguous state.

---

## 2. Implemented Fix & Architectural Safeguards

1. **Failure & Ambiguity Precedence:**
   `result_analysis_node` now evaluates zero matches and ambiguities for both rooms and staff first:
   - If `search_rooms` returned 0 matches: Immediately halt with `Room Not Found`.
   - If `search_staff` returned 0 matches: Immediately halt with `Staff Member Not Found`.
   - If either returned multiple ambiguous matches: Prompt the user for clarification.
2. **Unified Clinical Intent Detection:**
   Replaced hardcoded word lists with `_is_task_creation_request(message)`, which parses:
   - Explicit natural language ("create task", "schedule a clinical task", etc.)
   - Clinical procedure verbs ("steriliz", "restock", "sanitiz", "post-op", "autoclave", etc.)
   - Comma-separated parameter shorthand (`<title>,<room>,<date>,<priority>,<staff>`).
3. **Hard False-Success Interception (Double Gate):**
   In both `agent_reasoning_node` and `report_synthesis_node`:
   ```python
   if _claims_task_creation(reply) and not _has_verified_task_creation(tool_results, executed):
       reply = (
           f"### ⚠️ Action Intercepted by PractiCare Governance\n\n"
           f"> **Error [PERSISTENCE_NOT_VERIFIED]:** Task creation claimed without verified database write in tenant `{context.tenant_id}`.\n\n"
           f"The task was not persisted to PostgreSQL. Please specify a valid room or provider to schedule this clinical task."
       )
   ```

---

## 3. Database-Backed Verification Results

### 3.1 Test Case 1: Non-Existent Staff (`Kavi`) in `tenant-001`
- **Input:** `Post-op Sterilization & Restock,102,2026-10-15,High,Kavi`
- **Executed Tools:** `['search_staff']`
- **AI Response:**
  ```markdown
  ### 🔍 Staff Member Not Found

  No clinical staff matching **"Kavi"** was found in tenant `tenant-001`.

  Please verify the provider name or check the staff directory before assigning this clinical task.
  ```
- **PostgreSQL Verification:** Zero tasks inserted.
- **Result:** **PASSED** (Truthful rejection, zero false success).

### 3.2 Test Case 2: Valid Staff (`Marcus`) in `tenant-001` (Deterministic Mode)
- **Input:** `Post-op Sterilization & Restock,102,2026-10-15,High,Marcus`
- **Executed Tools:** `['search_staff', 'search_rooms', 'create_clinical_task']`
- **AI Response:**
  ```markdown
  ### ✅ Clinical Task Scheduled
  - **Title:** **Post-op Sterilization & Restock**
  - **Priority:** `High`
  - **Task ID:** `tsk-14f3ad47`
  - **Assigned Provider:** Marcus Chen, RN (Nurse)
  - **Room:** `room-102`
  - **Due Date:** `2026-10-15`
  ```
- **PostgreSQL Verification:**
  `SELECT id, title, room_id, assigned_staff_id, tenant_id FROM tasks WHERE id = 'tsk-14f3ad47'`
  Returned: `tsk-14f3ad47 | Post-op Sterilization & Restock | room-102 | stf-02 | tenant-001`.
- **Result:** **PASSED** (Real database persistence confirmed).

### 3.3 Test Case 3: Isolated Tenant with Staff `Kavi` & Room `102`
- **Setup:** Disposable test tenant with Room 102 and Nurse Kavi.
- **Input:** `Post-op Sterilization & Restock,102,2026-10-15,High,Kavi`
- **Executed Tools:** `['search_staff', 'search_rooms', 'create_clinical_task']`
- **PostgreSQL Verification:** 1 task persisted with `title = 'Post-op Sterilization & Restock'`, `room_id = room.id`, `assigned_staff_id = kavi.id`, `priority = 'High'`.
- **Result:** **PASSED**.

### 3.4 Test Case 4: Live Google Gemini 3.1 Flash-Lite Tool Calling Flow
- **Setup:** Isolated test tenant with Room 102 and Nurse Marcus.
- **Input:** `"Please create a high-priority clinical task titled Clean and Restock Suite for Room 102 assigned to Marcus due tomorrow."`
- **Live Gemini Execution Trace:** `['search_rooms', 'search_staff', 'create_clinical_task']`
- **Live Gemini Response:**
  ```markdown
  Task successfully created.

  * **Task ID:** tsk-608d37ae
  * **Title:** Clean and Restock Suite
  * **Priority:** High
  * **Status:** Created
  * **Assignee:** Marcus Chen (stf-3d40cde9)
  * **Room:** Room 102 — Pediatric Care Room (room-5e330280)
  ```
- **PostgreSQL Verification:**
  `Persisted: ID=tsk-608d37ae, Title=Clean and Restock Suite, Room=room-5e330280, Staff=stf-3d40cde9`
- **Result:** **PASSED** (Real multi-step Gemini tool calling and PostgreSQL write verified).
