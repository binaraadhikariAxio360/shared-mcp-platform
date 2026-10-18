"""
PractiCare MOC identity-linking & leave-approval regression tests (isolated in-memory SQLite).

- Staff identity is linked only through Staff.user_id; a matching name never grants another person's record.
- Leave requests from self-service start PENDING; only Owner/Doctor approve; nobody but the Owner self-approves.
"""

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

PASSWORD = "TestPass1!"


def _user(uid, role, full_name=None, tenant="tenant-a"):
    return models.User(
        id=uid, email=f"{uid}@test.local", password_hash=hash_password(PASSWORD), full_name=full_name or uid,
        role=role, tenant_id=tenant, company_name=tenant, membership_status="APPROVED", is_active=True,
    )


class IdentityAndLeaveRegressionTests(PractiCareIsolatedTestCase):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add_all([
            _user("mgr-a", "INVENTORY_MANAGER"),
            _user("doc-a", "ATTENDING_PHYSICIAN"),
            # Same display name as an existing, unlinked roster entry that has assigned work
            _user("namesake-a", "NURSE_STAFF", full_name="Jordan Roster"),
            models.Staff(id="staff-mgr-a", name="Manager A", role="Inventory Manager", user_id="mgr-a", practice_id="practice-a", tenant_id="tenant-a"),
            models.Staff(id="staff-doc-a", name="Doctor A", role="Doctor", user_id="doc-a", practice_id="practice-a", tenant_id="tenant-a"),
            models.Staff(id="staff-roster", name="Jordan Roster", role="Nurse", user_id=None, practice_id="practice-a", tenant_id="tenant-a"),
            models.Staff(id="staff-b", name="Staff B", role="Nurse", practice_id="practice-b", tenant_id="tenant-b"),
            models.Task(id="task-roster", title="Roster nurse task", status="Pending", due_date="2026-10-20", assigned_staff_id="staff-roster", practice_id="practice-a", tenant_id="tenant-a"),
            models.StaffLeave(id="leave-b", staff_id="staff-b", tenant_id="tenant-b", leave_type="HOLIDAY", start_date=datetime.utcnow(), end_date=datetime.utcnow() + timedelta(days=1), status="PENDING"),
        ])
        db.commit()
        db.close()

    def headers(self, uid):
        return self.login_headers(f"{uid}@test.local", PASSWORD)

    def staff_row(self, sid):
        db = self.Session()
        try:
            return db.query(models.Staff).filter_by(id=sid).first()
        finally:
            db.close()

    def leave_now(self, **extra):
        now = datetime.utcnow()
        return {"leave_type": "HOLIDAY", "start_date": (now - timedelta(hours=1)).isoformat(), "end_date": (now + timedelta(days=2)).isoformat(), **extra}

    # --- Identity linking ------------------------------------------------------------

    def test_login_does_not_link_staff_record_by_name(self):
        self.headers("namesake-a")
        self.assertIsNone(self.staff_row("staff-roster").user_id)

    def test_staff_me_creates_own_record_instead_of_claiming_namesake(self):
        res = self.client.get("/api/v1/staff/me", headers=self.headers("namesake-a"))
        self.assertEqual(res.status_code, 200, res.text)
        self.assertNotEqual(res.json()["id"], "staff-roster")
        self.assertEqual(res.json()["user_id"], "namesake-a")
        self.assertIsNone(self.staff_row("staff-roster").user_id)

    def test_namesake_cannot_see_or_complete_roster_members_task(self):
        h = self.headers("namesake-a")
        self.client.get("/api/v1/staff/me", headers=h)
        ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=h).json()}
        self.assertNotIn("task-roster", ids)
        self.assertEqual(self.client.put("/api/v1/tasks/task-roster", json={"status": "Completed"}, headers=h).status_code, 403)

    def test_namesake_cannot_toggle_roster_members_shift(self):
        res = self.client.put("/api/v1/staff/staff-roster/shift", json={"on_shift": False}, headers=self.headers("namesake-a"))
        self.assertEqual(res.status_code, 403, res.text)
        self.assertIsNone(self.staff_row("staff-roster").user_id)

    def test_deactivating_user_does_not_touch_namesake_staff_record(self):
        res = self.client.put("/api/v1/users/namesake-a/status", json={"is_active": False}, headers=self.owner_a_headers())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(self.staff_row("staff-roster").is_active)

    # --- Leave approval ----------------------------------------------------------------

    def test_nurse_self_leave_is_pending_even_if_client_claims_approved(self):
        res = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(status="APPROVED"), headers=self.nurse_a_headers())
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["status"], "PENDING")
        nurse = self.staff_row("staff-nurse-a")
        self.assertEqual(nurse.work_status, "ACTIVE")
        self.assertTrue(nurse.on_shift)

    def test_doctor_approves_nurse_leave_and_status_applies(self):
        leave = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(), headers=self.nurse_a_headers()).json()
        self.assertEqual(
            self.client.put(f"/api/v1/staff/staff-nurse-a/leaves/{leave['id']}/status", json={"status": "APPROVED"}, headers=self.nurse_a_headers()).status_code,
            403,
        )
        res = self.client.put(f"/api/v1/staff/staff-nurse-a/leaves/{leave['id']}/status", json={"status": "APPROVED"}, headers=self.headers("doc-a"))
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "APPROVED")
        nurse = self.staff_row("staff-nurse-a")
        self.assertEqual(nurse.work_status, "HOLIDAY")
        self.assertFalse(nurse.on_shift)

    def test_rejected_leave_leaves_status_unchanged(self):
        leave = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(), headers=self.nurse_a_headers()).json()
        res = self.client.put(f"/api/v1/staff/staff-nurse-a/leaves/{leave['id']}/status", json={"status": "REJECTED"}, headers=self.owner_a_headers())
        self.assertEqual(res.json()["status"], "REJECTED")
        self.assertEqual(self.staff_row("staff-nurse-a").work_status, "ACTIVE")

    def test_doctor_cannot_self_approve_but_owner_can_approve_doctor(self):
        h = self.headers("doc-a")
        leave = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(status="APPROVED"), headers=h).json()
        self.assertEqual(leave["status"], "PENDING")
        self.assertEqual(self.client.put(f"/api/v1/staff/staff-doc-a/leaves/{leave['id']}/status", json={"status": "APPROVED"}, headers=h).status_code, 403)
        res = self.client.put(f"/api/v1/staff/staff-doc-a/leaves/{leave['id']}/status", json={"status": "APPROVED"}, headers=self.owner_a_headers())
        self.assertEqual(res.status_code, 200, res.text)

    def test_owner_own_leave_is_recorded_directly(self):
        res = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(), headers=self.owner_a_headers())
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["status"], "APPROVED")

    def test_manager_cannot_approve_leave(self):
        leave = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(), headers=self.nurse_a_headers()).json()
        res = self.client.put(f"/api/v1/staff/staff-nurse-a/leaves/{leave['id']}/status", json={"status": "APPROVED"}, headers=self.headers("mgr-a"))
        self.assertEqual(res.status_code, 403, res.text)

    def test_leave_review_validates_status_and_tenant(self):
        h = self.owner_a_headers()
        leave = self.client.post("/api/v1/staff/me/leaves", json=self.leave_now(), headers=self.nurse_a_headers()).json()
        self.assertEqual(self.client.put(f"/api/v1/staff/staff-nurse-a/leaves/{leave['id']}/status", json={"status": "MAYBE"}, headers=h).status_code, 400)
        self.assertEqual(self.client.put("/api/v1/staff/staff-b/leaves/leave-b/status", json={"status": "APPROVED"}, headers=h).status_code, 404)

    def test_ai_self_holiday_by_doctor_is_pending_but_dnd_applies(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "doc-a", "ATTENDING_PHYSICIAN")
        res = gateway.execute("set_staff_work_status", {"staff_id": "staff-doc-a", "work_status": "HOLIDAY"}, ctx, db)
        db.close()
        self.assertEqual(res.get("leave_status"), "PENDING", res)
        self.assertIn("PENDING", res["message"])
        self.assertEqual(self.staff_row("staff-doc-a").work_status, "ACTIVE")

        db = self.Session()
        res = gateway.execute("set_staff_work_status", {"staff_id": "staff-doc-a", "work_status": "DND"}, ctx, db)
        db.close()
        self.assertEqual(self.staff_row("staff-doc-a").work_status, "DND", res)

    def test_ai_doctor_sets_nurse_holiday_directly(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "doc-a", "ATTENDING_PHYSICIAN")
        res = gateway.execute("set_staff_work_status", {"staff_id": "staff-nurse-a", "work_status": "HOLIDAY"}, ctx, db)
        db.close()
        self.assertEqual(res.get("leave_status"), "APPROVED", res)
        self.assertEqual(self.staff_row("staff-nurse-a").work_status, "HOLIDAY")


if __name__ == "__main__":
    unittest.main()
