"""
PractiCare security & authorization regression tests (isolated in-memory SQLite, no live services).

One focused test (or small group) per security fix made on 2026-10-17:
1. Doctors cannot see Owner/Manager tasks via REST, AI tools, analytics, conflict reports or internal tools.
2. Doctors manage only Doctor/Nurse-scope tasks, assign only to Nurses or themselves, never delete self-assigned tasks.
3. Nurses complete only their own tasks/checklists; they can view every checklist in their tenant.
4. Nurses cannot create leave or change work status for other staff.
5. CLINICAL_AUDITOR is read-only.
6. Role permissions are aligned across REST, Tool Registry, Gateway and handlers (no gateway RBAC bypass).
8. Tenant isolation and token-derived identity on the affected paths.
"""

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "apps" / "practicare" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from practicare_phase0_harness import PractiCareIsolatedTestCase, models
from database import hash_password
from ai.context import SecurityContext
from ai.gateway import gateway
from ai.registry import registry

OWNER_SECRET = "OWNER-ONLY Payroll Review"
MANAGER_SECRET = "MANAGER-ONLY Vendor Contract"
PASSWORD = "TestPass1!"


def _user(uid, role, tenant="tenant-a"):
    return models.User(
        id=uid, email=f"{uid}@test.local", password_hash=hash_password(PASSWORD), full_name=uid,
        role=role, tenant_id=tenant, company_name=tenant, membership_status="APPROVED", is_active=True,
    )


def _staff(sid, name, role, user_id=None, tenant="tenant-a", practice="practice-a"):
    return models.Staff(id=sid, name=name, role=role, user_id=user_id, practice_id=practice, tenant_id=tenant)


def _task(tid, title, assigned=None, created_by_role=None, tenant="tenant-a", practice="practice-a", created_by_user_id=None):
    return models.Task(
        id=tid, title=title, status="Pending", due_date="2026-01-01", assigned_staff_id=assigned,
        created_by_role=created_by_role, created_by_user_id=created_by_user_id, practice_id=practice, tenant_id=tenant,
    )


class SecurityAuthorizationRegressionTests(PractiCareIsolatedTestCase):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add_all([
            _user("mgr-a", "INVENTORY_MANAGER"),
            _user("doc-a", "ATTENDING_PHYSICIAN"),
            _user("doc2-a", "ATTENDING_PHYSICIAN"),
            _user("nurse2-a", "NURSE_STAFF"),
            _user("aud-a", "CLINICAL_AUDITOR"),
            _staff("staff-mgr-a", "Manager A", "Inventory Manager", "mgr-a"),
            _staff("staff-doc-a", "Doctor A", "Doctor", "doc-a"),
            _staff("staff-doc2-a", "Doctor Two", "Doctor", "doc2-a"),
            _staff("staff-nurse2-a", "Nurse Two", "Nurse", "nurse2-a"),
            _staff("staff-b", "Staff B", "Nurse", None, "tenant-b", "practice-b"),
            _task("task-owner", OWNER_SECRET, created_by_role="CLINIC_OWNER"),
            _task("task-mgr", MANAGER_SECRET, assigned="staff-mgr-a"),
            _task("task-doc-own", "Doctor own task", assigned="staff-doc-a", created_by_role="ATTENDING_PHYSICIAN"),
            _task("task-nurse", "Nurse task", assigned="staff-nurse-a", created_by_role="ATTENDING_PHYSICIAN", created_by_user_id="doc-a"),
            _task("task-nurse2", "Nurse two task", assigned="staff-nurse2-a", created_by_role="ATTENDING_PHYSICIAN"),
            _task("task-b", "Tenant B task", tenant="tenant-b", practice="practice-b"),
            models.Checklist(id="check-nurse2", title="Nurse two checklist", assigned_staff_id="staff-nurse2-a", practice_id="practice-a", tenant_id="tenant-a"),
            models.Checklist(id="check-b", title="Tenant B checklist", practice_id="practice-b", tenant_id="tenant-b"),
        ])
        db.commit()
        db.close()

    # --- helpers --------------------------------------------------------------

    def headers(self, uid):
        return self.login_headers(f"{uid}@test.local", PASSWORD)

    def tool(self, uid, role, name, args, tenant="tenant-a"):
        db = self.Session()
        try:
            return gateway.execute(name, args, SecurityContext.create(tenant, uid, role), db)
        finally:
            db.close()

    def task_row(self, tid):
        db = self.Session()
        try:
            return db.query(models.Task).filter_by(id=tid).first()
        finally:
            db.close()

    def assert_no_restricted_titles(self, payload):
        dumped = json.dumps(payload, default=str)
        self.assertNotIn(OWNER_SECRET, dumped)
        self.assertNotIn(MANAGER_SECRET, dumped)

    # --- 1. Doctor visibility of Owner/Manager tasks --------------------------

    def test_doctor_rest_task_list_and_detail_exclude_owner_manager_tasks(self):
        h = self.headers("doc-a")
        ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=h).json()}
        self.assertTrue({"task-doc-own", "task-nurse", "task-nurse2"} <= ids, ids)
        self.assertFalse({"task-owner", "task-mgr"} & ids, ids)
        self.assertEqual(self.client.get("/api/v1/tasks/task-owner", headers=h).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/tasks/task-mgr", headers=h).status_code, 403)

    def test_doctor_ai_task_tools_exclude_owner_manager_tasks(self):
        self.assertEqual(self.tool("doc-a", "ATTENDING_PHYSICIAN", "get_task_details", {"task_id": "task-owner"}).get("error"), "FORBIDDEN")
        self.assert_no_restricted_titles(self.tool("doc-a", "ATTENDING_PHYSICIAN", "list_tasks", {}))

    def test_doctor_analytics_excludes_owner_manager_tasks(self):
        result = self.tool("doc-a", "ATTENDING_PHYSICIAN", "get_team_task_performance", {})
        self.assertNotIn("error", result, result)
        self.assert_no_restricted_titles(result)

    def test_doctor_conflict_reports_exclude_owner_manager_tasks(self):
        ai_result = self.tool("doc-a", "ATTENDING_PHYSICIAN", "get_operational_task_conflicts", {})
        self.assertNotIn("error", ai_result, ai_result)
        self.assert_no_restricted_titles(ai_result)

        rest = self.client.get("/api/v1/tasks/conflicts", headers=self.headers("doc-a"))
        self.assertEqual(rest.status_code, 200, rest.text)  # route was previously shadowed by /tasks/{task_id}
        self.assert_no_restricted_titles(rest.json())

    def test_doctor_internal_tool_excludes_owner_manager_tasks(self):
        res = self.client.post("/internal/tools/practicare.list_tasks", json={}, headers=self.headers("doc-a"))
        self.assertEqual(res.status_code, 200, res.text)
        self.assert_no_restricted_titles(res.json())

    def test_owner_and_manager_still_see_all_tenant_tasks(self):
        for uid, h in (("owner-a", self.owner_a_headers()), ("mgr-a", self.headers("mgr-a"))):
            ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=h).json()}
            self.assertTrue({"task-owner", "task-mgr", "task-nurse"} <= ids, (uid, ids))
            self.assertNotIn("task-b", ids)
        conflicts = self.client.get("/api/v1/tasks/conflicts", headers=self.owner_a_headers()).json()
        self.assertIn(OWNER_SECRET, json.dumps(conflicts))

    # --- 2. Doctor task management ---------------------------------------------

    def test_doctor_cannot_modify_or_delete_owner_manager_tasks(self):
        h = self.headers("doc-a")
        self.assertEqual(self.client.put("/api/v1/tasks/task-owner", json={"priority": "High"}, headers=h).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/tasks/task-mgr", headers=h).status_code, 403)
        self.assertIsNotNone(self.task_row("task-mgr"))

    def test_doctor_cannot_delete_self_assigned_task(self):
        res = self.client.delete("/api/v1/tasks/task-doc-own", headers=self.headers("doc-a"))
        self.assertEqual(res.status_code, 403, res.text)
        self.assertIsNotNone(self.task_row("task-doc-own"))

    def test_doctor_can_delete_nurse_task_in_scope(self):
        self.assertEqual(self.client.delete("/api/v1/tasks/task-nurse", headers=self.headers("doc-a")).status_code, 204)
        self.assertIsNone(self.task_row("task-nurse"))

    def test_doctor_assigns_only_to_nurses_or_self(self):
        h = self.headers("doc-a")
        base = {"title": "Doctor created", "priority": "Medium", "status": "Pending", "due_date": "2026-10-20"}
        self.assertEqual(self.client.post("/api/v1/tasks", json={**base, "assigned_staff_id": "staff-nurse-a"}, headers=h).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/tasks", json={**base, "assigned_staff_id": "staff-doc-a"}, headers=h).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/tasks", json={**base, "assigned_staff_id": "staff-doc2-a"}, headers=h).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/tasks", json={**base, "assigned_staff_id": "staff-mgr-a"}, headers=h).status_code, 403)

        reassign = self.client.put("/api/v1/tasks/task-nurse", json={"assigned_staff_id": "staff-doc2-a"}, headers=h)
        self.assertEqual(reassign.status_code, 403, reassign.text)
        self.assertEqual(self.task_row("task-nurse").assigned_staff_id, "staff-nurse-a")

        ai_result = self.tool("doc-a", "ATTENDING_PHYSICIAN", "create_clinical_task", {"title": "AI task", "assigned_staff_id": "staff-doc2-a", "due_date": "2026-10-20"})
        self.assertIn("error", ai_result, ai_result)

    # --- 3. Nurse scope ----------------------------------------------------------

    def test_nurse_sees_only_own_tasks(self):
        ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=self.nurse_a_headers()).json()}
        self.assertEqual(ids, {"task-nurse"})
        analytics = self.tool("nurse-a", "NURSE_STAFF", "get_team_task_performance", {})
        self.assertEqual({t["task_id"] for t in analytics["operational_tasks"]}, {"task-nurse"})

    def test_nurse_cannot_complete_other_nurse_task_or_checklist(self):
        h = self.nurse_a_headers()
        self.assertEqual(self.client.put("/api/v1/tasks/task-nurse2", json={"status": "Completed"}, headers=h).status_code, 403)
        self.assertEqual(self.task_row("task-nurse2").status, "Pending")
        self.assertEqual(self.client.put("/api/v1/tasks/task-nurse", json={"status": "Completed"}, headers=h).status_code, 200)

        res = self.tool("nurse-a", "NURSE_STAFF", "update_checklist_status", {"checklist_id": "check-nurse2", "is_completed": True})
        self.assertEqual(res.get("error"), "FORBIDDEN", res)

    def test_nurse_cannot_use_checklist_definition_tool(self):
        # The gateway previously skipped allowed_roles when a policy pre-check passed.
        res = self.tool("nurse-a", "NURSE_STAFF", "update_checklist", {"checklist_id": "check-nurse2", "title": "Renamed"})
        self.assertEqual(res.get("error"), "FORBIDDEN", res)

    def test_nurse_views_all_checklists_in_own_tenant_only(self):
        ids = {c["id"] for c in self.client.get("/api/v1/checklists", headers=self.nurse_a_headers()).json()}
        self.assertTrue({"check-a", "check-nurse2"} <= ids, ids)
        self.assertNotIn("check-b", ids)

    # --- 4. Leave / work status ----------------------------------------------------

    def _leave_payload(self):
        now = datetime.utcnow()
        return {"leave_type": "HOLIDAY", "start_date": now.isoformat(), "end_date": (now + timedelta(days=2)).isoformat()}

    def test_nurse_cannot_create_leave_or_set_status_for_other_staff(self):
        h = self.nurse_a_headers()
        self.assertEqual(self.client.post("/api/v1/staff/staff-nurse2-a/leaves", json=self._leave_payload(), headers=h).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/staff/staff-nurse2-a/work-status", json={"work_status": "DND"}, headers=h).status_code, 403)
        db = self.Session()
        self.assertEqual(db.query(models.StaffLeave).filter_by(staff_id="staff-nurse2-a").count(), 0)
        self.assertEqual(db.query(models.Staff).filter_by(id="staff-nurse2-a").first().work_status, "ACTIVE")
        db.close()

    def test_nurse_can_manage_own_leave(self):
        res = self.client.post("/api/v1/staff/me/leaves", json=self._leave_payload(), headers=self.nurse_a_headers())
        self.assertEqual(res.status_code, 201, res.text)

    def test_nurse_cannot_delete_other_staff_leave(self):
        created = self.client.post("/api/v1/staff/staff-nurse2-a/leaves", json=self._leave_payload(), headers=self.headers("doc-a"))
        self.assertEqual(created.status_code, 201, created.text)  # Doctor holds staff:leave_manage
        res = self.client.delete(f"/api/v1/staff/staff-nurse2-a/leaves/{created.json()['id']}", headers=self.nurse_a_headers())
        self.assertEqual(res.status_code, 403, res.text)

    def test_ai_work_status_tool_not_available_to_nurse(self):
        res = self.tool("nurse-a", "NURSE_STAFF", "set_staff_work_status", {"staff_id": "staff-nurse2-a", "work_status": "DND"})
        self.assertEqual(res.get("error"), "FORBIDDEN", res)

    # --- 5. Auditor is read-only ---------------------------------------------------

    def test_auditor_cannot_write_via_rest(self):
        h = self.headers("aud-a")
        base = {"title": "Audit", "priority": "Medium", "status": "Pending", "due_date": "2026-10-20"}
        self.assertEqual(self.client.post("/api/v1/tasks", json=base, headers=h).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/tasks/task-nurse", json={"status": "Completed"}, headers=h).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/tasks/task-nurse", headers=h).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/checklists/check-a", json={"is_completed": True}, headers=h).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/checklists/check-a", headers=h).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/rooms/room-a", json={"status": "Turnover"}, headers=h).status_code, 403)
        self.assertEqual(self.task_row("task-nurse").status, "Pending")

    def test_auditor_cannot_write_via_ai(self):
        res = self.tool("aud-a", "CLINICAL_AUDITOR", "update_task_status", {"task_id": "task-nurse", "status": "Completed"})
        self.assertEqual(res.get("error"), "FORBIDDEN", res)
        self.assertEqual(self.task_row("task-nurse").status, "Pending")

    def test_auditor_reads_without_owner_manager_tasks(self):
        res = self.client.get("/api/v1/tasks", headers=self.headers("aud-a"))
        self.assertEqual(res.status_code, 200, res.text)
        ids = {t["id"] for t in res.json()}
        self.assertNotIn("task-owner", ids)
        self.assertIn("task-nurse", ids)

    # --- 6. Cross-layer alignment ----------------------------------------------------

    def test_manager_can_use_task_and_room_read_tools(self):
        visible = {t.name for t in registry.get_tools_for_role("INVENTORY_MANAGER")}
        self.assertTrue({"list_tasks", "get_room_turnover_status", "search_rooms"} <= visible, visible)
        for name in ("list_tasks", "get_room_turnover_status", "get_team_task_performance"):
            res = self.tool("mgr-a", "INVENTORY_MANAGER", name, {})
            self.assertNotIn("error", res, (name, res))

    def test_doctor_may_change_room_status_only(self):
        h = self.headers("doc-a")
        self.assertEqual(self.client.put("/api/v1/rooms/room-a", json={"status": "Turnover"}, headers=h).status_code, 200)
        self.assertEqual(self.client.put("/api/v1/rooms/room-a", json={"name": "Renamed"}, headers=h).status_code, 403)
        res = self.tool("doc-a", "ATTENDING_PHYSICIAN", "update_room", {"room_id": "room-a", "name": "Renamed"})
        self.assertEqual(res.get("error"), "FORBIDDEN", res)

    def test_doctor_cannot_add_room_or_manage_inventory(self):
        h = self.headers("doc-a")
        self.assertEqual(self.client.post("/api/v1/rooms", json={"room_number": "Z1", "name": "Z"}, headers=h).status_code, 403)
        self.assertEqual(self.tool("doc-a", "ATTENDING_PHYSICIAN", "create_room", {"room_number": "Z1", "name": "Z"}).get("error"), "FORBIDDEN")

    # --- 8. Tenant isolation & identity --------------------------------------------

    def test_cross_tenant_task_access_is_blocked(self):
        h = self.owner_a_headers()
        self.assertEqual(self.client.get("/api/v1/tasks/task-b", headers=h).status_code, 404)
        self.assertEqual(self.client.put("/api/v1/tasks/task-b", json={"status": "Completed"}, headers=h).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/staff/staff-b/leaves", json=self._leave_payload(), headers=h).status_code, 404)
        res = self.tool("owner-a", "CLINIC_OWNER", "update_task_status", {"task_id": "task-b", "status": "Completed"})
        self.assertIn("error", res, res)
        self.assertEqual(self.task_row("task-b").status, "Pending")
        self.assertNotIn("Tenant B task", json.dumps(self.client.get("/api/v1/tasks/conflicts", headers=h).json()))

    def test_identity_comes_from_token_not_headers(self):
        spoofed = {**self.owner_b_headers(), "X-Tenant-Id": "tenant-a", "X-User-Role": "CLINIC_OWNER", "X-User-Id": "owner-a"}
        ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=spoofed).json()}
        self.assertEqual(ids, {"task-b"})
        self.assertEqual(self.client.get("/api/v1/tasks", headers={"Authorization": "Bearer forged.token"}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/tasks").status_code, 401)


if __name__ == "__main__":
    unittest.main()
