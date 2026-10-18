"""
PractiCare runtime & role regression tests (isolated in-memory SQLite, no live services).

Covers bugs confirmed on 2026-10-17:
- Doctors stored with legacy role 'PHYSICIAN' were denied task create/update (403) and AI chat (500).
- Nurses could never complete their own task / tick their own checklist through the Tool Gateway.
- The sequential agent fallback (no LangGraph installed) crashed with KeyError: 'message'.
- Unhandled agent errors produced CORS-less 500s, shown in the browser as "Failed to fetch".
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1] / "apps" / "practicare" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from practicare_phase0_harness import PractiCareIsolatedTestCase, models
import main
from database import hash_password
from ai.context import SecurityContext, normalize_role
from ai.gateway import gateway
from ai.agent import agent

# ai/__init__ re-exports the `agent` instance, shadowing the submodule attribute
agent_module = sys.modules["ai.agent"]


class RuntimeAndRoleRegressionTests(PractiCareIsolatedTestCase):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add_all([
            models.User(id="phys-a", email="phys-a@test.local", password_hash=hash_password("PhysPass1!"), full_name="Physician A", role="PHYSICIAN", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.Staff(id="staff-phys-a", name="Physician A", role="Doctor", user_id="phys-a", practice_id="practice-a", tenant_id="tenant-a"),
            models.Staff(id="staff-other-nurse", name="Other Nurse", role="Nurse", practice_id="practice-a", tenant_id="tenant-a"),
            models.Task(id="task-nurse-own", title="Nurse own task", status="Pending", due_date="2026-10-20", assigned_staff_id="staff-nurse-a", practice_id="practice-a", tenant_id="tenant-a"),
            models.Task(id="task-other-nurse", title="Other nurse task", status="Pending", due_date="2026-10-20", assigned_staff_id="staff-other-nurse", practice_id="practice-a", tenant_id="tenant-a"),
            models.Checklist(id="check-nurse-own", title="Nurse own checklist", is_completed=False, assigned_staff_id="staff-nurse-a", practice_id="practice-a", tenant_id="tenant-a"),
        ])
        db.commit()
        db.close()

    def physician_headers(self):
        return self.login_headers("phys-a@test.local", "PhysPass1!")

    # --- Role normalization -------------------------------------------------

    def test_role_aliases_normalize_to_canonical_roles(self):
        self.assertEqual(normalize_role("physician"), "ATTENDING_PHYSICIAN")
        self.assertEqual(normalize_role(" DOCTOR "), "ATTENDING_PHYSICIAN")
        self.assertEqual(normalize_role("OWNER"), "CLINIC_OWNER")
        self.assertEqual(normalize_role("NURSE"), "NURSE_STAFF")
        self.assertEqual(normalize_role("CLINIC_OWNER"), "CLINIC_OWNER")
        self.assertEqual(SecurityContext.create("tenant-a", "phys-a", "PHYSICIAN").user_role, "ATTENDING_PHYSICIAN")

    def test_physician_role_can_create_and_update_task_via_rest(self):
        headers = self.physician_headers()
        created = self.client.post(
            "/api/v1/tasks",
            json={"title": "Doctor saved task", "priority": "Medium", "status": "Pending", "due_date": "2026-10-20", "assigned_staff_id": "staff-nurse-a"},
            headers=headers,
        )
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["id"]

        updated = self.client.put(f"/api/v1/tasks/{task_id}", json={"priority": "High"}, headers=headers)
        self.assertEqual(updated.status_code, 200, updated.text)

        db = self.Session()
        row = db.query(models.Task).filter_by(id=task_id).first()
        self.assertEqual(row.priority, "High")
        self.assertEqual(row.created_by_role, "ATTENDING_PHYSICIAN")
        db.close()

    def test_physician_role_cannot_add_room(self):
        res = self.client.post("/api/v1/rooms", json={"room_number": "X9", "name": "X Room"}, headers=self.physician_headers())
        self.assertEqual(res.status_code, 403, res.text)

    def test_invitation_role_is_normalized_and_unknown_roles_rejected(self):
        headers = self.owner_a_headers()
        ok = self.client.post("/api/v1/company/invitations", json={"role": "PHYSICIAN"}, headers=headers)
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["role"], "ATTENDING_PHYSICIAN")

        bad = self.client.post("/api/v1/company/invitations", json={"role": "SUPERUSER"}, headers=headers)
        self.assertEqual(bad.status_code, 400, bad.text)

    # --- Nurse self-service through the Tool Gateway ------------------------

    def test_nurse_completes_own_task_via_gateway_and_persists(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        result = gateway.execute("update_task_status", {"task_id": "task-nurse-own", "status": "Completed"}, ctx, db)
        self.assertNotIn("error", result, result)
        db.close()

        db = self.Session()
        self.assertEqual(db.query(models.Task).filter_by(id="task-nurse-own").first().status, "Completed")
        db.close()

    def test_nurse_cannot_complete_other_users_task_via_gateway(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        result = gateway.execute("update_task_status", {"task_id": "task-other-nurse", "status": "Completed"}, ctx, db)
        self.assertEqual(result.get("error"), "FORBIDDEN", result)
        self.assertEqual(db.query(models.Task).filter_by(id="task-other-nurse").first().status, "Pending")
        db.close()

    def test_nurse_cannot_reassign_own_task_via_gateway(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        result = gateway.execute("update_task_status", {"task_id": "task-nurse-own", "assigned_staff_id": "staff-other-nurse"}, ctx, db)
        self.assertEqual(result.get("error"), "FORBIDDEN", result)
        self.assertEqual(db.query(models.Task).filter_by(id="task-nurse-own").first().assigned_staff_id, "staff-nurse-a")
        db.close()

    def test_nurse_ticks_own_checklist_via_gateway_and_persists(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        result = gateway.execute("update_checklist_status", {"checklist_id": "check-nurse-own", "is_completed": True}, ctx, db)
        self.assertNotIn("error", result, result)
        db.close()

        db = self.Session()
        self.assertTrue(db.query(models.Checklist).filter_by(id="check-nurse-own").first().is_completed)
        db.close()

    # --- Agent runtime without LangGraph / LangChain ------------------------

    def test_sequential_fallback_runs_without_langchain(self):
        db = self.Session()
        ctx = SecurityContext.create("tenant-a", "owner-a", "CLINIC_OWNER")
        with mock.patch.object(agent, "workflow", None), mock.patch.object(agent_module, "ToolMessage", None):
            result = agent.run(message="List all pending tasks", conversation_history=[], context=ctx, db=db, agent_mode="deterministic")
        db.close()
        self.assertTrue(result.get("reply"))
        self.assertIn("list_tasks", [t["tool"] for t in result["tool_calls_executed"]])

    # --- Chat endpoint error handling ----------------------------------------

    def test_chat_agent_failure_returns_json_error_with_cors_headers(self):
        headers = {**self.owner_a_headers(), "Origin": "http://localhost:3001"}
        with mock.patch.object(main.agent, "run", side_effect=RuntimeError("boom")):
            res = self.client.post("/api/v1/ai/chat", json={"message": "hello"}, headers=headers)
        self.assertEqual(res.status_code, 500, res.text)
        self.assertIn("failed to process", res.json()["detail"])
        self.assertNotIn("boom", res.text)
        self.assertEqual(res.headers.get("access-control-allow-origin"), "http://localhost:3001")

    def test_physician_can_use_ai_chat(self):
        res = self.client.post(
            "/api/v1/ai/chat",
            json={"message": "List all pending tasks", "agent_mode": "deterministic"},
            headers=self.physician_headers(),
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["reply"])


if __name__ == "__main__":
    unittest.main()
