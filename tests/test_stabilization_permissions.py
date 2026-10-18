"""
PractiCare AI Stabilization Regression Test Suite
Tests:
- Every existing role and its permissions
- Assigned task completion (REST and AI Tool Gateway)
- Assigned checklist ticking (REST and AI Tool Gateway)
- Assigned user deletion denial (tasks and checklists)
- Unauthorized user modification denial (scope limitation)
- Cross-tenant isolation (tasks and checklists)
- REST and AI authorization parity
- Real database persistence verification
- Missing-record handling (no fabrication)
- Failed tool execution (no state change)
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "apps" / "practicare" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from practicare_phase0_harness import PractiCareIsolatedTestCase, models
from database import hash_password
from ai.context import SecurityContext
from ai.gateway import gateway
from ai.agent import agent


class PractiCareStabilizationPermissionTests(PractiCareIsolatedTestCase):
    def setUp(self):
        super().setUp()
        db = self.Session()

        # Seed additional users and staff for all defined roles
        doc_user = models.User(
            id="doc-a",
            email="doc-a@test.local",
            password_hash=hash_password("DocPass1!"),
            full_name="Doctor A",
            role="ATTENDING_PHYSICIAN",
            tenant_id="tenant-a",
            company_name="Clinic A",
            membership_status="APPROVED",
            is_active=True,
        )
        inv_user = models.User(
            id="inv-a",
            email="inv-a@test.local",
            password_hash=hash_password("InvPass1!"),
            full_name="Inventory Staff A",
            role="INVENTORY_MANAGER",
            tenant_id="tenant-a",
            company_name="Clinic A",
            membership_status="APPROVED",
            is_active=True,
        )
        inv_user_b = models.User(
            id="inv-b",
            email="inv-b@test.local",
            password_hash=hash_password("InvPass1!"),
            full_name="Inventory Staff B",
            role="INVENTORY_MANAGER",
            tenant_id="tenant-b",
            company_name="Clinic B",
            membership_status="APPROVED",
            is_active=True,
        )

        doc_staff = models.Staff(
            id="staff-doc-a",
            name="Doctor A",
            role="Doctor",
            user_id="doc-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )
        inv_staff = models.Staff(
            id="staff-inv-a",
            name="Inventory A",
            role="Staff",
            user_id="inv-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )

        # Assigned tasks
        task_inv = models.Task(
            id="task-assigned-inv",
            title="Restock syringe inventory",
            status="Pending",
            priority="Medium",
            due_date="2026-10-20",
            assigned_staff_id="staff-inv-a",
            room_id="room-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )
        task_nurse = models.Task(
            id="task-assigned-nurse",
            title="Disinfect Room A1",
            status="Pending",
            priority="High",
            due_date="2026-10-20",
            assigned_staff_id="staff-nurse-a",
            room_id="room-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )

        # Assigned checklists
        chk_inv = models.Checklist(
            id="check-assigned-inv",
            title="Inspect PPE storage expiration",
            category="Inventory",
            is_completed=False,
            assigned_staff_id="staff-inv-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )
        chk_nurse = models.Checklist(
            id="check-assigned-nurse",
            title="Autoclave surgical tray A1",
            category="Sterilization",
            is_completed=False,
            assigned_staff_id="staff-nurse-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )

        # Tenant B records
        task_b = models.Task(
            id="task-b",
            title="Tenant B Private Task",
            status="Pending",
            due_date="2026-10-20",
            practice_id="practice-b",
            tenant_id="tenant-b",
        )
        chk_b = models.Checklist(
            id="check-b",
            title="Tenant B Private Checklist",
            category="Hygiene",
            is_completed=False,
            practice_id="practice-b",
            tenant_id="tenant-b",
        )

        db.add_all([
            doc_user, inv_user, inv_user_b,
            doc_staff, inv_staff,
            task_inv, task_nurse, chk_inv, chk_nurse,
            task_b, chk_b,
        ])
        db.commit()
        db.close()

    def doc_a_headers(self):
        return self.login_headers("doc-a@test.local", "DocPass1!")

    def inv_a_headers(self):
        return self.login_headers("inv-a@test.local", "InvPass1!")

    def inv_b_headers(self):
        return self.login_headers("inv-b@test.local", "InvPass1!")

    # -------------------------------------------------------------------------
    # Priority 4: Assigned Task Permissions (REST & AI parity)
    # -------------------------------------------------------------------------
    def test_assigned_user_can_view_own_task(self):
        """Rule 1: Authenticated user can view tasks assigned to them within tenant."""
        res = self.client.get("/api/v1/tasks/task-assigned-inv", headers=self.inv_a_headers())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["id"], "task-assigned-inv")
        self.assertEqual(res.json()["title"], "Restock syringe inventory")

    def test_nurse_cannot_view_others_task(self):
        """Nurse can complete own assigned task, cannot view others' tasks."""
        res = self.client.get("/api/v1/tasks/task-assigned-inv", headers=self.nurse_a_headers())
        self.assertEqual(res.status_code, 403, res.text)

    def test_manager_can_view_staff_tasks(self):
        """Manager can view and manage company staff tasks."""
        res = self.client.get("/api/v1/tasks/task-assigned-nurse", headers=self.inv_a_headers())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["id"], "task-assigned-nurse")

    def test_assigned_user_can_complete_own_task_via_rest(self):
        """Rule 2 & 8: Authenticated user can complete own assigned task regardless of role (persisted)."""
        res = self.client.put(
            "/api/v1/tasks/task-assigned-inv",
            headers=self.inv_a_headers(),
            json={"status": "Completed"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "Completed")

        # Database persistence check
        db = self.Session()
        t = db.query(models.Task).filter_by(id="task-assigned-inv").one()
        self.assertEqual(t.status, "Completed")
        db.close()

    def test_assigned_user_can_complete_own_task_via_ai_gateway(self):
        """Rule 9: AI Tool Gateway permits assigned user to complete own task (REST & AI parity)."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "inv-a", "INVENTORY_MANAGER")
        result = gateway.execute(
            "update_task_status",
            {"task_id": "task-assigned-inv", "status": "Completed"},
            context,
            db,
        )
        self.assertEqual(result.get("status"), "SUCCESS")
        self.assertEqual(result.get("updated_status"), "Completed")

        t = db.query(models.Task).filter_by(id="task-assigned-inv").one()
        self.assertEqual(t.status, "Completed")
        db.close()

    def test_nurse_cannot_reassign_or_modify_scope(self):
        """Nurse can only complete assigned tasks (status update only)."""
        res = self.client.put(
            "/api/v1/tasks/task-assigned-nurse",
            headers=self.nurse_a_headers(),
            json={"status": "In Progress", "priority": "Critical"},
        )
        self.assertEqual(res.status_code, 403, res.text)

        # State remained unchanged
        db = self.Session()
        t = db.query(models.Task).filter_by(id="task-assigned-nurse").one()
        self.assertEqual(t.priority, "High")
        db.close()

    def test_manager_can_modify_task_priority(self):
        """Manager can edit and update task attributes."""
        res = self.client.put(
            "/api/v1/tasks/task-assigned-nurse",
            headers=self.inv_a_headers(),
            json={"priority": "Critical"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["priority"], "Critical")

    def test_assigned_user_cannot_delete_assigned_task(self):
        """Manager and Doctor cannot delete a task assigned to themselves. Nurse cannot delete any task."""
        # Manager assigned user tries to delete own task
        res = self.client.delete("/api/v1/tasks/task-assigned-inv", headers=self.inv_a_headers())
        self.assertEqual(res.status_code, 403, res.text)

        # Nurse tries to delete task assigned to them
        res_nurse = self.client.delete("/api/v1/tasks/task-assigned-nurse", headers=self.nurse_a_headers())
        self.assertEqual(res_nurse.status_code, 403, res_nurse.text)

        # Database persistence: task was NOT deleted
        db = self.Session()
        self.assertIsNotNone(db.query(models.Task).filter_by(id="task-assigned-inv").first())
        self.assertIsNotNone(db.query(models.Task).filter_by(id="task-assigned-nurse").first())
        db.close()

    def test_manager_can_delete_task(self):
        """Manager and Doctor can delete tasks not assigned to themselves."""
        # Manager deletes nurse's task
        res = self.client.delete("/api/v1/tasks/task-assigned-nurse", headers=self.inv_a_headers())
        self.assertEqual(res.status_code, 204, res.text)

        db = self.Session()
        self.assertIsNone(db.query(models.Task).filter_by(id="task-assigned-nurse").first())
        db.close()

    def test_cross_tenant_task_access_forbidden(self):
        """Rule 7: Users cannot access or modify tasks belonging to another tenant."""
        # View cross-tenant task
        res_view = self.client.get("/api/v1/tasks/task-b", headers=self.inv_a_headers())
        self.assertEqual(res_view.status_code, 404)

        # Modify cross-tenant task
        res_mod = self.client.put(
            "/api/v1/tasks/task-b",
            headers=self.inv_a_headers(),
            json={"status": "Completed"},
        )
        self.assertEqual(res_mod.status_code, 404)

        # AI gateway cross-tenant rejection
        db = self.Session()
        context = SecurityContext.create("tenant-a", "inv-a", "INVENTORY_MANAGER")
        res_ai = gateway.execute(
            "update_task_status",
            {"task_id": "task-b", "status": "Completed"},
            context,
            db,
        )
        self.assertIn("error", res_ai)

        # State of tenant B task unchanged
        t_b = db.query(models.Task).filter_by(id="task-b").one()
        self.assertEqual(t_b.status, "Pending")
        db.close()

    # -------------------------------------------------------------------------
    # Priority 5: Assigned Checklist Permissions (REST & AI parity)
    # -------------------------------------------------------------------------
    def test_assigned_user_can_view_own_checklist(self):
        """Rule 1: Assigned users can view their assigned checklists."""
        res = self.client.get("/api/v1/checklists/check-assigned-inv", headers=self.inv_a_headers())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["id"], "check-assigned-inv")

    def test_assigned_user_can_tick_and_untick_checklist_via_rest(self):
        """Rule 2 & 3: Assigned users can tick or untick assigned checklists (persisted)."""
        # Tick (complete)
        res_tick = self.client.put(
            "/api/v1/checklists/check-assigned-inv",
            headers=self.inv_a_headers(),
            json={"is_completed": True},
        )
        self.assertEqual(res_tick.status_code, 200, res_tick.text)
        self.assertTrue(res_tick.json()["is_completed"])

        db = self.Session()
        chk = db.query(models.Checklist).filter_by(id="check-assigned-inv").one()
        self.assertTrue(chk.is_completed)

        # Untick (incomplete)
        res_untick = self.client.put(
            "/api/v1/checklists/check-assigned-inv",
            headers=self.inv_a_headers(),
            json={"is_completed": False},
        )
        self.assertEqual(res_untick.status_code, 200, res_untick.text)
        self.assertFalse(res_untick.json()["is_completed"])

        db.refresh(chk)
        self.assertFalse(chk.is_completed)
        db.close()

    def test_assigned_user_can_tick_checklist_via_ai_gateway(self):
        """Rule 7: REST and AI tools enforce identical checklist completion rules."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "inv-a", "INVENTORY_MANAGER")
        result = gateway.execute(
            "update_checklist_status",
            {"checklist_id": "check-assigned-inv", "is_completed": True},
            context,
            db,
        )
        self.assertEqual(result.get("status"), "SUCCESS")
        self.assertTrue(result.get("is_completed"))

        chk = db.query(models.Checklist).filter_by(id="check-assigned-inv").one()
        self.assertTrue(chk.is_completed)
        db.close()

    def test_nurse_cannot_delete_checklist(self):
        """Nurse cannot delete any checklist definition."""
        res = self.client.delete("/api/v1/checklists/check-assigned-nurse", headers=self.nurse_a_headers())
        self.assertEqual(res.status_code, 403, res.text)

        # Via AI Gateway
        db = self.Session()
        context = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        res_ai = gateway.execute(
            "delete_clinical_checklist",
            {"checklist_id": "check-assigned-nurse"},
            context,
            db,
        )
        self.assertEqual(res_ai.get("error"), "FORBIDDEN")

        # Database record preserved
        self.assertIsNotNone(db.query(models.Checklist).filter_by(id="check-assigned-nurse").first())
        db.close()

    def test_manager_can_delete_checklist(self):
        """Manager can delete checklists."""
        res = self.client.delete("/api/v1/checklists/check-assigned-inv", headers=self.inv_a_headers())
        self.assertEqual(res.status_code, 204, res.text)

        db = self.Session()
        self.assertIsNone(db.query(models.Checklist).filter_by(id="check-assigned-inv").first())
        db.close()

    def test_nurse_cannot_modify_other_users_checklist_or_definition(self):
        """Nurse can view all company checklists, but cannot modify other users' checklists or definitions."""
        # Nurse views all checklists in company
        res_view = self.client.get("/api/v1/checklists/check-assigned-inv", headers=self.nurse_a_headers())
        self.assertEqual(res_view.status_code, 200)

        # Nurse tries to complete checklist assigned to manager
        res = self.client.put(
            "/api/v1/checklists/check-assigned-inv",
            headers=self.nurse_a_headers(),
            json={"is_completed": True},
        )
        self.assertEqual(res.status_code, 403, res.text)

        # Nurse tries to change category or title on their own checklist
        res_scope = self.client.put(
            "/api/v1/checklists/check-assigned-nurse",
            headers=self.nurse_a_headers(),
            json={"title": "Hacked Title", "category": "General"},
        )
        self.assertEqual(res_scope.status_code, 403, res_scope.text)

    def test_manager_can_update_checklist_definition(self):
        """Manager can edit title, category, and assignment on checklists."""
        res = self.client.put(
            "/api/v1/checklists/check-assigned-inv",
            headers=self.inv_a_headers(),
            json={"title": "Updated PPE Title", "category": "Safety"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["title"], "Updated PPE Title")

        db = self.Session()
        chk = db.query(models.Checklist).filter_by(id="check-assigned-inv").one()
        self.assertEqual(chk.title, "Updated PPE Title")
        db.close()

    def test_cross_tenant_checklist_isolation(self):
        """Rule 6: Cross-tenant checklist access is forbidden."""
        res_view = self.client.get("/api/v1/checklists/check-b", headers=self.inv_a_headers())
        self.assertEqual(res_view.status_code, 404)

        res_mod = self.client.put(
            "/api/v1/checklists/check-b",
            headers=self.inv_a_headers(),
            json={"is_completed": True},
        )
        self.assertEqual(res_mod.status_code, 404)

    # -------------------------------------------------------------------------
    # Priority 2 & 7: Truthful AI Data Flows (No fabrication, real queries)
    # -------------------------------------------------------------------------
    def test_missing_record_returns_truthful_error(self):
        """Missing record returns error, never fabricates dummy results."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "owner-a", "CLINIC_OWNER")
        result = gateway.execute(
            "get_task_details",
            {"task_id": "tsk-nonexistent-999"},
            context,
            db,
        )
        self.assertEqual(result.get("error"), "EXECUTION_ERROR")
        self.assertIn("not found", result.get("detail", "").lower())
        db.close()

    def test_ai_agent_shows_real_assigned_tasks(self):
        """AI agent retrieves real assigned tasks for authenticated user."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "inv-a", "INVENTORY_MANAGER")
        response = agent.run(
            message="Show my assigned tasks",
            conversation_history=[],
            context=context,
            db=db,
            conversation_id="conv-test-1",
        )
        self.assertIn("Restock syringe inventory", response["reply"])
        self.assertIn("task-assigned-inv", response["reply"])
        db.close()

    def test_ai_agent_shows_real_assigned_checklists(self):
        """AI agent retrieves real assigned checklists for authenticated user."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "inv-a", "INVENTORY_MANAGER")
        response = agent.run(
            message="Show my checklists",
            conversation_history=[],
            context=context,
            db=db,
            conversation_id="conv-test-2",
        )
        self.assertIn("Inspect PPE storage expiration", response["reply"])
        self.assertIn("check-assigned-inv", response["reply"])
        db.close()

    def test_ai_agent_ticks_assigned_checklist_item(self):
        """AI agent ticks assigned checklist item and verifies DB persistence."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "inv-a", "INVENTORY_MANAGER")
        response = agent.run(
            message="Tick checklist check-assigned-inv",
            conversation_history=[],
            context=context,
            db=db,
            conversation_id="conv-test-3",
        )
        self.assertIn("Checklist Status Updated", response["reply"])
        self.assertIn("check-assigned-inv", response["reply"])

        # Verify PostgreSQL / DB state actually changed
        chk = db.query(models.Checklist).filter_by(id="check-assigned-inv").one()
        self.assertTrue(chk.is_completed)
        db.close()


    def test_doctor_can_assign_task_to_nurse_but_not_to_manager_or_owner(self):
        """Doctor can assign tasks to Nurses, but cannot assign to Manager or Owner."""
        # Doctor assigns to nurse -> 201
        res_nurse = self.client.post(
            "/api/v1/tasks",
            headers=self.doc_a_headers(),
            json={
                "title": "Doctor Task for Nurse",
                "room_id": "room-a",
                "assigned_staff_id": "staff-nurse-a",
                "priority": "Medium",
                "due_date": "2026-10-20",
            },
        )
        self.assertEqual(res_nurse.status_code, 201, res_nurse.text)

        # Doctor tries to assign to Owner -> 403
        res_owner = self.client.post(
            "/api/v1/tasks",
            headers=self.doc_a_headers(),
            json={
                "title": "Doctor Task for Owner",
                "room_id": "room-a",
                "assigned_staff_id": "staff-owner-a",
                "priority": "High",
                "due_date": "2026-10-20",
            },
        )
        self.assertEqual(res_owner.status_code, 403, res_owner.text)

        # Doctor tries to assign to Manager -> 403
        res_mgr = self.client.post(
            "/api/v1/tasks",
            headers=self.doc_a_headers(),
            json={
                "title": "Doctor Task for Manager",
                "room_id": "room-a",
                "assigned_staff_id": "staff-inv-a",
                "priority": "High",
                "due_date": "2026-10-20",
            },
        )
        self.assertEqual(res_mgr.status_code, 403, res_mgr.text)

    def test_doctor_cannot_edit_or_delete_owner_or_manager_task(self):
        """Doctor cannot edit or delete Owner/Manager tasks, nor delete self-assigned tasks."""
        db = self.Session()
        owner_task = models.Task(
            id="task-created-by-owner",
            title="Owner Executive Review",
            status="Pending",
            priority="Critical",
            due_date="2026-10-20",
            created_by_role="CLINIC_OWNER",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )
        doc_self_task = models.Task(
            id="task-assigned-to-doc",
            title="Doctor Self Task",
            status="Pending",
            due_date="2026-10-20",
            assigned_staff_id="staff-doc-a",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )
        db.add_all([owner_task, doc_self_task])
        db.commit()
        db.close()

        # Doctor tries to edit Owner task -> 403
        res_edit = self.client.put(
            "/api/v1/tasks/task-created-by-owner",
            headers=self.doc_a_headers(),
            json={"priority": "Low"},
        )
        self.assertEqual(res_edit.status_code, 403, res_edit.text)

        # Doctor tries to delete Owner task -> 403
        res_del_owner = self.client.delete(
            "/api/v1/tasks/task-created-by-owner",
            headers=self.doc_a_headers(),
        )
        self.assertEqual(res_del_owner.status_code, 403, res_del_owner.text)

        # Doctor tries to delete task assigned to themselves -> 403
        res_del_self = self.client.delete(
            "/api/v1/tasks/task-assigned-to-doc",
            headers=self.doc_a_headers(),
        )
        self.assertEqual(res_del_self.status_code, 403, res_del_self.text)

    def test_doctor_cannot_retrieve_restricted_owner_or_manager_task_via_ai(self):
        """Doctor cannot retrieve restricted Owner/Manager task details through AI."""
        db = self.Session()
        owner_task = models.Task(
            id="task-secret-owner",
            title="Executive Salary Audit",
            status="Pending",
            due_date="2026-10-20",
            created_by_role="CLINIC_OWNER",
            practice_id="practice-a",
            tenant_id="tenant-a",
        )
        db.add(owner_task)
        db.commit()

        context = SecurityContext.create("tenant-a", "doc-a", "ATTENDING_PHYSICIAN")
        result = gateway.execute(
            "get_task_details",
            {"task_id": "task-secret-owner"},
            context,
            db,
        )
        self.assertEqual(result.get("error"), "FORBIDDEN")
        db.close()

    def test_doctor_can_change_room_status_but_cannot_add_room(self):
        """Doctor can change room status, but cannot create rooms."""
        # Doctor changes room status -> 200
        res_status = self.client.put(
            "/api/v1/rooms/room-a",
            headers=self.doc_a_headers(),
            json={"status": "Occupied"},
        )
        self.assertEqual(res_status.status_code, 200, res_status.text)
        self.assertEqual(res_status.json()["status"], "Occupied")

        # Doctor tries to add room -> 403
        res_add = self.client.post(
            "/api/v1/rooms",
            headers=self.doc_a_headers(),
            json={"room_number": "DOC-99", "name": "Doctor Room", "room_type": "Exam"},
        )
        self.assertEqual(res_add.status_code, 403, res_add.text)

    def test_nurse_cannot_create_task_or_checklist(self):
        """Nurse cannot create tasks or checklists."""
        res_task = self.client.post(
            "/api/v1/tasks",
            headers=self.nurse_a_headers(),
            json={"title": "Nurse Unauthorized Task", "room_id": "room-a", "due_date": "2026-10-20"},
        )
        self.assertEqual(res_task.status_code, 403, res_task.text)

        res_chk = self.client.post(
            "/api/v1/checklists",
            headers=self.nurse_a_headers(),
            json={"title": "Nurse Unauthorized Checklist"},
        )
        self.assertEqual(res_chk.status_code, 403, res_chk.text)

    def test_nurse_cannot_modify_inventory_or_change_room_status(self):
        """Nurse has read-only access to inventory and rooms, cannot mutate."""
        # Nurse views inventory -> 200
        res_inv_view = self.client.get("/api/v1/inventory", headers=self.nurse_a_headers())
        self.assertEqual(res_inv_view.status_code, 200)

        # Nurse views rooms -> 200
        res_rooms_view = self.client.get("/api/v1/rooms", headers=self.nurse_a_headers())
        self.assertEqual(res_rooms_view.status_code, 200)

        # Nurse tries to add inventory item -> 403
        res_inv_add = self.client.post(
            "/api/v1/inventory",
            headers=self.nurse_a_headers(),
            json={"item_name": "Bandages", "current_stock": 50, "min_threshold": 10},
        )
        self.assertEqual(res_inv_add.status_code, 403, res_inv_add.text)

        # Nurse tries to change room status -> 403
        res_room_status = self.client.put(
            "/api/v1/rooms/room-a",
            headers=self.nurse_a_headers(),
            json={"status": "Available"},
        )
        self.assertEqual(res_room_status.status_code, 403, res_room_status.text)

    def test_nurse_can_ask_ai_for_inventory_summary(self):
        """Nurse can ask AI for inventory summaries (read-only)."""
        db = self.Session()
        context = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        result = gateway.execute(
            "get_inventory_status",
            {"low_stock_only": False},
            context,
            db,
        )
        self.assertEqual(result.get("status"), "SUCCESS")
        db.close()

    def test_manager_can_manage_inventory_and_add_rooms(self):
        """Manager can add rooms, change room status, and manage inventory."""
        # Manager adds room -> 201
        res_room = self.client.post(
            "/api/v1/rooms",
            headers=self.inv_a_headers(),
            json={"room_number": "MGR-101", "name": "Manager Storage", "room_type": "Storage"},
        )
        self.assertEqual(res_room.status_code, 201, res_room.text)
        created_room_id = res_room.json()["id"]

        # Manager changes room status -> 200
        res_status = self.client.put(
            f"/api/v1/rooms/{created_room_id}",
            headers=self.inv_a_headers(),
            json={"status": "Occupied"},
        )
        self.assertEqual(res_status.status_code, 200, res_status.text)

        # Manager creates inventory item -> 201
        res_inv = self.client.post(
            "/api/v1/inventory",
            headers=self.inv_a_headers(),
            json={"item_name": "Latex Gloves", "current_stock": 200, "min_threshold": 50},
        )
        self.assertEqual(res_inv.status_code, 201, res_inv.text)
        item_id = res_inv.json()["id"]

        # Manager updates inventory item -> 200
        res_inv_update = self.client.put(
            f"/api/v1/inventory/{item_id}",
            headers=self.inv_a_headers(),
            json={"current_stock": 180},
        )
        self.assertEqual(res_inv_update.status_code, 200, res_inv_update.text)
        self.assertEqual(res_inv_update.json()["current_stock"], 180)

        # Manager deletes inventory item -> 204
        res_inv_del = self.client.delete(
            f"/api/v1/inventory/{item_id}",
            headers=self.inv_a_headers(),
        )
        self.assertEqual(res_inv_del.status_code, 204, res_inv_del.text)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
