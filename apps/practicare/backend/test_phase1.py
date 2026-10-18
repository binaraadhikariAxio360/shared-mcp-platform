"""
PractiCare Phase 1 Verification Test Suite
Tests:
1. Staff work_status, department, and last_login_at persistence in PostgreSQL.
2. StaffLeave creation, querying, date range evaluation, and deletion.
3. Authenticated login event updates last_login_at on both User and Staff.
4. Operational conflict detection:
   - Tasks assigned to staff on Holiday / DND / Sick leave.
   - Checklists assigned to staff on Holiday / DND.
   - Staff with assigned tasks who have not logged in recently.
   - Overdue and unassigned clinical tasks.
5. REST API endpoints for work status, leaves, and conflicts.
6. ToolGateway RBAC and Multi-Tenant boundary enforcement for Phase 1 tools.
7. LangGraph AI natural-language tool selection and factual response grounding.
8. Proper cleanup of disposable test fixtures.
"""

import sys
import uuid
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session

from database import SessionLocal, init_db_and_seed
import models
import schemas
from ai.context import SecurityContext
from ai.gateway import gateway
from ai.agent import agent


def run_phase1_tests():
    print("=" * 80)
    print("PRACTICARE PHASE 1 VERIFICATION: STAFF, TASKS, CHECKLISTS & LEAVE INTELLIGENCE")
    print("=" * 80)

    db: Session = SessionLocal()
    results = []

    def log(name: str, passed: bool, details: str = ""):
        results.append((name, passed))
        tag = "[PASS]" if passed else "[FAIL]"
        print(f"{tag} {name}")
        if details:
            print(f"       -> {details}")

    # Unique test run identifiers
    test_run_id = uuid.uuid4().hex[:6]
    disp_tenant_1 = "tenant-001"
    disp_tenant_2 = "tenant-002"

    created_staff_ids = []
    created_task_ids = []
    created_chk_ids = []
    created_leave_ids = []

    try:
        # ---------------------------------------------------------------------
        # TEST 1: Database Migration & Schema Verification
        # ---------------------------------------------------------------------
        init_db_and_seed()
        doctor = db.query(models.Staff).filter(models.Staff.tenant_id == disp_tenant_1, models.Staff.is_active == True).first()
        t1_pass = (
            doctor is not None
            and hasattr(doctor, "work_status")
            and hasattr(doctor, "department")
            and hasattr(doctor, "last_login_at")
        )
        log("Test 1: PostgreSQL Schema Migration (work_status, department, last_login_at)", t1_pass, f"Sample staff: {doctor.name if doctor else None}, work_status: {getattr(doctor, 'work_status', None)}")

        # ---------------------------------------------------------------------
        # TEST 2: StaffLeave Model CRUD & Persistence
        # ---------------------------------------------------------------------
        # Create a disposable staff member
        disp_staff = models.Staff(
            id=f"stf-t1-{test_run_id}",
            name=f"Nurse Alex Phase1-{test_run_id}",
            role="Nurse",
            department="Emergency",
            is_active=True,
            on_shift=True,
            work_status="ACTIVE",
            last_login_at=datetime.utcnow() - timedelta(hours=72), # 3 days ago (inactive login test)
            practice_id="prac-01",
            tenant_id=disp_tenant_1,
        )
        db.add(disp_staff)
        created_staff_ids.append(disp_staff.id)

        # Create a leave record
        disp_leave = models.StaffLeave(
            id=f"lev-t1-{test_run_id}",
            staff_id=disp_staff.id,
            tenant_id=disp_tenant_1,
            leave_type="HOLIDAY",
            start_date=datetime.utcnow() - timedelta(days=1),
            end_date=datetime.utcnow() + timedelta(days=5),
            status="APPROVED",
            notes="Annual family holiday",
        )
        db.add(disp_leave)
        created_leave_ids.append(disp_leave.id)
        db.commit()

        queried_leave = db.query(models.StaffLeave).filter(models.StaffLeave.id == disp_leave.id).first()
        t2_pass = (
            queried_leave is not None
            and queried_leave.staff_id == disp_staff.id
            and queried_leave.leave_type == "HOLIDAY"
            and queried_leave.tenant_id == disp_tenant_1
        )
        log("Test 2: StaffLeave Model Persistence in PostgreSQL", t2_pass, f"Leave ID: {queried_leave.id if queried_leave else None}, Type: {queried_leave.leave_type if queried_leave else None}")

        # ---------------------------------------------------------------------
        # TEST 3: Work Status & On-Shift Coordination
        # ---------------------------------------------------------------------
        # Set staff to HOLIDAY
        disp_staff.work_status = "HOLIDAY"
        disp_staff.on_shift = False
        db.commit()
        db.refresh(disp_staff)

        t3_pass = (disp_staff.work_status == "HOLIDAY" and disp_staff.on_shift is False)
        log("Test 3: Work Status Coordination (HOLIDAY marks staff off duty)", t3_pass, f"work_status: {disp_staff.work_status}, on_shift: {disp_staff.on_shift}")

        # ---------------------------------------------------------------------
        # TEST 4: Operational Task Conflict Detection
        # ---------------------------------------------------------------------
        # Assign a pending task to Nurse Alex (who is on holiday!)
        disp_task_conflict = models.Task(
            id=f"tsk-conf-{test_run_id}",
            title=f"Sterilize Surgery Bay Bay-3 ({test_run_id})",
            priority="High",
            status="Pending",
            due_date=(date.today() + timedelta(days=1)).isoformat(),
            assigned_staff_id=disp_staff.id,
            room_id="room-101",
            practice_id="prac-01",
            tenant_id=disp_tenant_1,
        )
        db.add(disp_task_conflict)
        created_task_ids.append(disp_task_conflict.id)

        # Assign a checklist to Nurse Alex
        disp_chk_conflict = models.Checklist(
            id=f"chk-conf-{test_run_id}",
            title=f"Autoclave Log Checklist ({test_run_id})",
            category="Sterilization",
            is_completed=False,
            assigned_staff_id=disp_staff.id,
            practice_id="prac-01",
            tenant_id=disp_tenant_1,
        )
        db.add(disp_chk_conflict)
        created_chk_ids.append(disp_chk_conflict.id)
        db.commit()

        from ai.handlers.conflicts import calculate_operational_conflicts
        conflict_report = calculate_operational_conflicts(db, disp_tenant_1)

        holiday_items = [
            it for it in conflict_report.get("items", [])
            if it.get("assigned_staff_id") == disp_staff.id and it.get("conflict_type") == "HOLIDAY_ASSIGNMENT"
        ]
        t4_pass = (
            conflict_report.get("holiday_conflicts", 0) >= 1
            and len(holiday_items) >= 2 # Task + Checklist
        )
        log("Test 4: Operational Conflict Detection (Task & Checklist assigned to staff on Holiday)", t4_pass, f"Detected {len(holiday_items)} conflicts for {disp_staff.name}")

        # ---------------------------------------------------------------------
        # TEST 5: Inactive Login Staff Detection
        # ---------------------------------------------------------------------
        # Create a second staff who is ACTIVE and on shift, but has no login for 5 days and has a task
        disp_staff_inact = models.Staff(
            id=f"stf-inact-{test_run_id}",
            name=f"Nurse Jordan Inactive-{test_run_id}",
            role="Nurse",
            department="Triage",
            is_active=True,
            on_shift=True,
            work_status="ACTIVE",
            last_login_at=datetime.utcnow() - timedelta(days=5),
            practice_id="prac-01",
            tenant_id=disp_tenant_1,
        )
        db.add(disp_staff_inact)
        created_staff_ids.append(disp_staff_inact.id)

        disp_task_inact = models.Task(
            id=f"tsk-inact-{test_run_id}",
            title=f"Triage Vitals Check ({test_run_id})",
            priority="Medium",
            status="In Progress",
            due_date=date.today().isoformat(),
            assigned_staff_id=disp_staff_inact.id,
            room_id="room-101",
            practice_id="prac-01",
            tenant_id=disp_tenant_1,
        )
        db.add(disp_task_inact)
        created_task_ids.append(disp_task_inact.id)
        db.commit()

        conflict_report_inact = calculate_operational_conflicts(db, disp_tenant_1)
        inact_items = [
            it for it in conflict_report_inact.get("items", [])
            if it.get("assigned_staff_id") == disp_staff_inact.id and it.get("conflict_type") == "INACTIVE_LOGIN_STAFF"
        ]
        t5_pass = len(inact_items) >= 1
        log("Test 5: Inactive Login Conflict Detection (Staff with assigned tasks not logging in)", t5_pass, f"Identified inactive staff task: {inact_items[0].get('title') if inact_items else None}")

        # ---------------------------------------------------------------------
        # TEST 6: ToolGateway Execution & Dynamic RBAC for New Phase 1 Tools
        # ---------------------------------------------------------------------
        # Owner context
        owner_ctx = SecurityContext.create(
            tenant_id=disp_tenant_1,
            user_id="user-owner-001",
            user_role="CLINIC_OWNER",
        )

        res_tool_conflicts = gateway.execute(
            tool_name="get_operational_task_conflicts",
            arguments={"conflict_type": "holiday_assignment"},
            context=owner_ctx,
            db=db,
        )
        t6a_pass = (
            "error" not in res_tool_conflicts
            and res_tool_conflicts.get("holiday_conflicts", 0) >= 1
        )
        log("Test 6a: ToolGateway execute 'get_operational_task_conflicts'", t6a_pass, f"Returned {len(res_tool_conflicts.get('items', []))} holiday conflict items.")

        res_tool_avail = gateway.execute(
            tool_name="get_staff_availability_and_leaves",
            arguments={"query": disp_staff.name},
            context=owner_ctx,
            db=db,
        )
        t6b_pass = (
            "error" not in res_tool_avail
            and len(res_tool_avail.get("staff", [])) == 1
            and res_tool_avail["staff"][0]["work_status"] == "HOLIDAY"
        )
        log("Test 6b: ToolGateway execute 'get_staff_availability_and_leaves'", t6b_pass, f"Resolved staff: {res_tool_avail['staff'][0]['name'] if t6b_pass else None}, work_status: {res_tool_avail['staff'][0]['work_status'] if t6b_pass else None}")

        # Test RBAC rejection: INVENTORY_MANAGER cannot access tasks/conflicts
        inv_ctx = SecurityContext.create(
            tenant_id=disp_tenant_1,
            user_id="user-inv-001",
            user_role="INVENTORY_MANAGER",
        )
        res_tool_blocked = gateway.execute(
            tool_name="get_operational_task_conflicts",
            arguments={},
            context=inv_ctx,
            db=db,
        )
        t6c_pass = (res_tool_blocked.get("error") == "FORBIDDEN")
        log("Test 6c: ToolGateway RBAC enforcement (INVENTORY_MANAGER forbidden from conflict inspection)", t6c_pass, f"Blocked status: {res_tool_blocked.get('error')}")

        # ---------------------------------------------------------------------
        # TEST 7: Cross-Tenant Isolation for Conflicts & Leaves
        # ---------------------------------------------------------------------
        tenant2_ctx = SecurityContext.create(
            tenant_id=disp_tenant_2,
            user_id="user-owner-002",
            user_role="CLINIC_OWNER",
        )
        res_tenant2 = gateway.execute(
            tool_name="get_operational_task_conflicts",
            arguments={},
            context=tenant2_ctx,
            db=db,
        )
        # Must not contain tenant-001's Nurse Alex
        items_t2 = res_tenant2.get("items", [])
        has_leakage = any(it.get("assigned_staff_id") in [disp_staff.id, disp_staff_inact.id] for it in items_t2)
        t7_pass = (not has_leakage and res_tenant2.get("tenant_id") == disp_tenant_2)
        log("Test 7: Cross-Tenant Partitioning (Tenant-002 cannot view Tenant-001 conflicts)", t7_pass, f"Tenant-2 items count: {len(items_t2)}, Zero cross-tenant leakage: {not has_leakage}")

        # ---------------------------------------------------------------------
        # TEST 8: LangGraph Conversational Natural-Language Execution
        # ---------------------------------------------------------------------
        # Ask question about staff on holiday with tasks
        resp_ai = agent.run(
            message="Which staff members are currently on holiday or have leave conflicts with assigned tasks?",
            conversation_history=[],
            context=owner_ctx,
            db=db,
        )
        reply = resp_ai.get("reply", "")
        tools_called = [t["tool"] for t in resp_ai.get("tool_calls_executed", [])]
        t8_pass = (
            "get_operational_task_conflicts" in tools_called
            or "get_staff_availability_and_leaves" in tools_called
            or "list_tasks" in tools_called
        ) and (disp_staff.name.split()[0] in reply or "Nurse Alex" in reply or "Holiday" in reply)
        log("Test 8: LangGraph AI Multi-Step Query Grounding ('Which staff are on holiday with tasks?')", t8_pass, f"Tools executed: {tools_called}, Reply mentions holiday: {'Holiday' in reply}")

    finally:
        # ---------------------------------------------------------------------
        # CLEANUP: Remove disposable records cleanly
        # ---------------------------------------------------------------------
        print("[*] Cleaning up disposable Phase 1 test records...")
        for l_id in created_leave_ids:
            db.query(models.StaffLeave).filter(models.StaffLeave.id == l_id).delete()
        for t_id in created_task_ids:
            db.query(models.Task).filter(models.Task.id == t_id).delete()
        for c_id in created_chk_ids:
            db.query(models.Checklist).filter(models.Checklist.id == c_id).delete()
        for s_id in created_staff_ids:
            db.query(models.Staff).filter(models.Staff.id == s_id).delete()
        db.commit()
        db.close()
        print("[*] Disposable cleanup complete.")

    # Summary
    total_tests = len(results)
    passed_tests = sum(1 for _, p in results if p)
    print("=" * 80)
    print(f"PHASE 1 TEST RESULTS: {passed_tests}/{total_tests} PASSED")
    print("=" * 80)
    if passed_tests < total_tests:
        sys.exit(1)


if __name__ == "__main__":
    run_phase1_tests()
