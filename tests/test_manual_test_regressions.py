"""
PractiCare MOC regressions for the 7 issues found in manual testing (2026-10-18).
Isolated in-memory SQLite; Gemini is replaced by a scripted fake model (no network, no quota).

Fixture mirrors tenant-easternwav-cd6b: Owner, Manager (Sagy), Doctors (Dr. Dem, Dr. Racini — stored role
PHYSICIAN), Nurse (Kavi); Owner-created tasks delegated to doctors; checklists created by Owner/Doctor.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1] / "apps" / "practicare" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from practicare_phase0_harness import PractiCareIsolatedTestCase, models
from database import hash_password
from ai.context import SecurityContext
from ai.gateway import gateway
from ai.agent import agent
from langchain_core.messages import AIMessage

agent_module = sys.modules["ai.agent"]
T = "tenant-e"
PASSWORD = "TestPass1!"


def _user(uid, role, name):
    return models.User(id=uid, email=f"{uid}@test.local", password_hash=hash_password(PASSWORD), full_name=name,
                       role=role, tenant_id=T, company_name="EW", membership_status="APPROVED", is_active=True)


def _staff(sid, name, role, uid):
    return models.Staff(id=sid, name=name, role=role, user_id=uid, practice_id="practice-e", tenant_id=T)


def _task(tid, title, assigned=None, creator=None, status="Pending", creator_uid=None):
    return models.Task(id=tid, title=title, status=status, due_date="2026-10-20", assigned_staff_id=assigned,
                       created_by_role=creator, created_by_user_id=creator_uid, practice_id="practice-e", tenant_id=T)


def _chk(cid, title, assigned=None, creator=None):
    return models.Checklist(id=cid, title=title, category="Hygiene", assigned_staff_id=assigned,
                            created_by_role=creator, practice_id="practice-e", tenant_id=T)


class FakeGemini:
    """Scripted stand-in for ChatGoogleGenerativeAI: tool-planning replies, then a synthesis reply."""

    def __init__(self, planning_replies, synthesis_text):
        self.planning = list(planning_replies)
        self.synthesis_text = synthesis_text
        self.synthesis_prompts = []

    def bind_tools(self, schemas):
        fake = self

        class Bound:
            def invoke(self, messages):
                return fake.planning.pop(0) if fake.planning else AIMessage(content="Done.")
        return Bound()

    def invoke(self, messages):
        self.synthesis_prompts.append(messages)
        return AIMessage(content=self.synthesis_text)


class ManualTestRegressionTests(PractiCareIsolatedTestCase):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add_all([
            models.Practice(id="practice-e", name="EW Clinic", location="EW", tenant_id=T),
            _user("own-e", "CLINIC_OWNER", "Owner E"),
            _user("mgr-e", "INVENTORY_MANAGER", "Sagy"),
            _user("dem-e", "PHYSICIAN", "Dr. Dem"),
            _user("rac-e", "PHYSICIAN", "Dr. Racini"),
            _user("kav-e", "NURSE_STAFF", "Kavi"),
            _staff("stf-own", "Owner E", "Staff", "own-e"),
            _staff("stf-mgr", "Sagy", "Inventory Manager", "mgr-e"),
            _staff("stf-dem", "Dr. Dem", "Doctor", "dem-e"),
            _staff("stf-rac", "Dr. Racini", "Doctor", "rac-e"),
            _staff("stf-kav", "Kavi", "Nurse", "kav-e"),
            models.Room(id="room-exam", room_number="102", name="Primary Exam Suite", status="Occupied", practice_id="practice-e", tenant_id=T),
            models.Room(id="room-nurse", room_number="01-N", name="Nursing Station", status="Available", practice_id="practice-e", tenant_id=T),
            _task("tsk-dem-own", "Check Clinic Opening Readiness", "stf-dem", "CLINIC_OWNER"),
            _task("tsk-rac-own", "Treatment Room Readiness Inspection", "stf-rac", "CLINIC_OWNER"),
            _task("tsk-kav", "Turnover & Bed Prep", "stf-kav"),
            _task("tsk-done", "Post-op Sterilization & Restock", "stf-rac", status="Completed"),
            _task("tsk-own-private", "OWNER-PRIVATE Payroll Review", None, "CLINIC_OWNER"),
            _task("tsk-mgr", "MANAGER-PRIVATE Vendor Contract", "stf-mgr", "CLINIC_OWNER"),
            _chk("chk-kav-own", "Nursing Station Daily Checklist", "stf-kav", "CLINIC_OWNER"),
            _chk("chk-mgr", "Medical Store Inventory Checklist", "stf-mgr", "CLINIC_OWNER"),
            _chk("chk-rac-doc", "Treatment Room Safety Checklist", "stf-rac", "ATTENDING_PHYSICIAN"),
        ])
        db.commit()
        db.close()

    # --- helpers -----------------------------------------------------------------------------

    def h(self, uid):
        return self.login_headers(f"{uid}@test.local", PASSWORD)

    def ctx(self, uid, role):
        return SecurityContext.create(T, uid, role)

    def run_agent(self, uid, role, message, fake):
        db = self.Session()
        try:
            with mock.patch.object(agent_module, "get_gemini_llm", return_value=(fake, "fake-gemini")), \
                 mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "test-only-not-a-key"}):
                return agent.run(message=message, conversation_history=[], context=self.ctx(uid, role), db=db, agent_mode="gemini")
        finally:
            db.close()

    def row(self, model, rid):
        db = self.Session()
        try:
            return db.query(model).filter_by(id=rid).first()
        finally:
            db.close()

    # --- Issue 1: consistent task visibility -------------------------------------------------------

    def test_issue1_doctor_sees_delegated_tasks_but_not_owner_or_manager_work(self):
        ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=self.h("dem-e")).json()}
        self.assertTrue({"tsk-dem-own", "tsk-rac-own", "tsk-kav", "tsk-done"} <= ids, ids)
        self.assertFalse({"tsk-own-private", "tsk-mgr"} & ids, ids)
        self.assertEqual(self.client.get("/api/v1/tasks/tsk-own-private", headers=self.h("dem-e")).status_code, 403)

    def test_issue1_dashboard_counts_match_task_list_for_every_role(self):
        for uid in ("own-e", "mgr-e", "dem-e", "rac-e", "kav-e"):
            hdr = self.h(uid)
            tasks = self.client.get("/api/v1/tasks", headers=hdr).json()
            summary = self.client.get("/api/v1/dashboard/summary", headers=hdr).json()
            pending = sum(1 for t in tasks if t["status"].lower() in ("pending", "in progress"))
            self.assertEqual(summary["tasks_total"], len(tasks), uid)
            self.assertEqual(summary["tasks_pending"], pending, uid)
        self.assertEqual(self.client.get("/api/v1/dashboard/summary", headers=self.h("kav-e")).json()["tasks_pending"], 1)

    def test_issue1_ai_task_tools_match_rest(self):
        for uid, role in (("dem-e", "PHYSICIAN"), ("kav-e", "NURSE_STAFF"), ("own-e", "CLINIC_OWNER")):
            rest = {t["id"] for t in self.client.get("/api/v1/tasks", headers=self.h(uid)).json()}
            db = self.Session()
            ai = gateway.execute("list_tasks", {}, self.ctx(uid, role), db)
            summary = gateway.execute("get_practice_summary", {}, self.ctx(uid, role), db)
            db.close()
            self.assertEqual({t["task_id"] for t in ai["tasks"]}, rest, uid)
            self.assertEqual(summary["clinical_operations"]["total_tasks"], len(rest), uid)

    # --- Issue 2: checklist creation persistence & duplicates ----------------------------------------

    def test_issue2_create_checklist_returns_persisted_id_and_assignee_and_is_idempotent(self):
        args = {"title": "Consultation Room Opening Checklist", "assigned_staff_id": "stf-dem", "category": "Hygiene"}
        db = self.Session()
        first = gateway.execute("create_checklist", dict(args), self.ctx("rac-e", "PHYSICIAN"), db)
        retry = gateway.execute("create_checklist", dict(args), self.ctx("rac-e", "PHYSICIAN"), db)
        count = db.query(models.Checklist).filter_by(tenant_id=T, title=args["title"]).count()
        db.close()
        self.assertTrue(first["persisted"])
        self.assertEqual(first["assigned_staff_name"], "Dr. Dem")
        self.assertFalse(first["duplicate_prevented"])
        self.assertEqual(retry["checklist_id"], first["checklist_id"])
        self.assertTrue(retry["duplicate_prevented"])
        self.assertEqual(count, 1)
        self.assertIn("line items are not stored", first["note"])

    def test_issue2_successful_checklist_creation_is_not_reported_as_failed(self):
        msg = ("Create a checklist titled 'Consultation Room Opening Checklist' and assign it to existing staff member "
               "Dr. Dem (staff ID: stf-dem). Add these items: 1. Confirm consultation room is clean 2. Check equipment")
        fake = FakeGemini(
            [AIMessage(content="", tool_calls=[{"name": "create_checklist", "id": "c1", "args": {
                "title": "Consultation Room Opening Checklist", "assigned_staff_id": "stf-dem", "category": "Hygiene"}}])],
            "PLACEHOLDER",
        )
        fake.synthesis_text = "The checklist has been created and assigned to Dr. Dem."
        result = self.run_agent("rac-e", "PHYSICIAN", msg, fake)
        self.assertNotIn("PERSISTENCE_NOT_VERIFIED", result["reply"])
        self.assertNotIn("Not Completed", result["reply"])
        self.assertIn("has been created", result["reply"])
        self.assertEqual([t["tool"] for t in result["tool_calls_executed"]], ["create_checklist"])

    def test_issue2_guard_still_blocks_unsupported_success_claims(self):
        fake = FakeGemini([AIMessage(content="The checklist has been created successfully with ID chk-zz99zz99.")], "")
        result = self.run_agent("own-e", "CLINIC_OWNER", "Create a checklist titled 'Imaginary'", fake)
        self.assertIn("PERSISTENCE_NOT_VERIFIED", result["reply"])
        db = self.Session()
        self.assertEqual(db.query(models.Checklist).filter_by(title="Imaginary").count(), 0)
        db.close()

    # --- Issue 3: doctor checklist edit -----------------------------------------------------------------

    def ui_edit(self, chk_id, uid, **override):
        chk = self.row(models.Checklist, chk_id)
        payload = {"title": chk.title + " (edited)", "category": chk.category, "frequency": "Weekly",
                   "assigned_staff_id": chk.assigned_staff_id}
        payload.update(override)
        return self.client.put(f"/api/v1/checklists/{chk_id}", json=payload, headers=self.h(uid))

    def test_issue3_doctor_saves_edit_of_owner_created_nurse_checklist(self):
        res = self.ui_edit("chk-kav-own", "dem-e")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.row(models.Checklist, "chk-kav-own").frequency, "Weekly")

    def test_issue3_doctor_edits_other_doctors_checklist_without_reassigning(self):
        self.assertEqual(self.ui_edit("chk-rac-doc", "dem-e").status_code, 200)

    def test_issue3_unauthorized_checklist_edits_still_denied(self):
        self.assertEqual(self.ui_edit("chk-mgr", "dem-e").status_code, 403)
        self.assertEqual(self.ui_edit("chk-kav-own", "dem-e", assigned_staff_id="stf-mgr").status_code, 403)
        self.assertEqual(self.ui_edit("chk-kav-own", "kav-e").status_code, 403)
        self.assertEqual(self.row(models.Checklist, "chk-mgr").title, "Medical Store Inventory Checklist")

    def test_issue3_checklist_permission_flags_match_policy(self):
        flags = {c["id"]: c for c in self.client.get("/api/v1/checklists", headers=self.h("dem-e")).json()}
        self.assertTrue(flags["chk-kav-own"]["can_edit"])
        self.assertFalse(flags["chk-mgr"]["can_edit"])
        nurse = {c["id"]: c for c in self.client.get("/api/v1/checklists", headers=self.h("kav-e")).json()}
        self.assertTrue(nurse["chk-kav-own"]["can_toggle"])
        self.assertFalse(nurse["chk-kav-own"]["can_edit"])
        self.assertFalse(nurse["chk-rac-doc"]["can_toggle"])

    # --- Issue 4: nurse completes own task --------------------------------------------------------------

    def test_issue4_nurse_task_flags_and_completion(self):
        hdr = self.h("kav-e")
        task = next(t for t in self.client.get("/api/v1/tasks", headers=hdr).json() if t["id"] == "tsk-kav")
        self.assertEqual((task["can_complete"], task["can_edit"], task["can_delete"]), (True, False, False))
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-kav", json={"status": "Completed"}, headers=hdr).status_code, 200)
        self.assertEqual(self.row(models.Task, "tsk-kav").status, "Completed")

    def test_issue4_nurse_cannot_edit_reassign_delete_or_create(self):
        hdr = self.h("kav-e")
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-dem-own", json={"status": "Completed"}, headers=hdr).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-kav", json={"assigned_staff_id": "stf-dem"}, headers=hdr).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-kav", json={"title": "Changed"}, headers=hdr).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-kav", headers=hdr).status_code, 403)
        self.assertEqual(self.client.post("/api/v1/tasks", json={"title": "x", "due_date": "2026-10-20"}, headers=hdr).status_code, 403)

    def test_issue4_doctor_completes_own_owner_delegated_task_but_cannot_delete_it(self):
        hdr = self.h("dem-e")
        task = next(t for t in self.client.get("/api/v1/tasks", headers=hdr).json() if t["id"] == "tsk-dem-own")
        self.assertTrue(task["can_complete"])
        self.assertFalse(task["can_delete"])
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-dem-own", json={"status": "Completed"}, headers=hdr).status_code, 200)

    # --- Issue 5: AI summary combines repeated tool calls ---------------------------------------------------

    def test_issue5_nurse_summary_sees_all_list_tasks_results(self):
        fake = FakeGemini(
            [AIMessage(content="", tool_calls=[
                {"name": "list_tasks", "id": "a", "args": {"status": "Pending"}},
                {"name": "list_tasks", "id": "b", "args": {"status": "In Progress"}},
            ])],
            "You have 1 pending task: Turnover & Bed Prep (tsk-kav).",
        )
        result = self.run_agent("kav-e", "NURSE_STAFF", "Give Task Summary", fake)
        evidence = fake.synthesis_prompts[-1][0].content
        self.assertEqual(evidence.count('"tool": "list_tasks"'), 2)
        self.assertIn("tsk-kav", evidence)  # the Pending result is no longer overwritten by the empty In Progress one
        self.assertIn("tsk-kav", result["reply"])

    def test_issue5_synthesis_does_not_force_unsolicited_analysis(self):
        fake = FakeGemini([AIMessage(content="", tool_calls=[{"name": "list_tasks", "id": "a", "args": {}}])], "ok")
        self.run_agent("own-e", "CLINIC_OWNER", "List my tasks", fake)
        prompt = fake.synthesis_prompts[-1][0].content
        self.assertNotIn("include comprehensive executive overview", prompt)
        self.assertIn("ONLY when the user asked for analysis", prompt)

    # --- Issue 6: read-only room requests -----------------------------------------------------------------

    def test_issue6_read_only_room_request_is_not_reported_as_failed_update(self):
        fake = FakeGemini(
            [AIMessage(content="", tool_calls=[{"name": "get_room_turnover_status", "id": "r", "args": {}}])],
            "Available rooms: Nursing Station (01-N).",
        )
        result = self.run_agent("kav-e", "NURSE_STAFF", "Give Available Room Details", fake)
        self.assertNotIn("not updated", result["reply"])
        self.assertIn("Nursing Station", result["reply"])

    def test_issue6_read_only_room_question_never_triggers_a_room_write(self):
        # Gemini answers without tools; the old keyword interceptor would have planned update_room(status=Available)
        fake = FakeGemini([AIMessage(content="Room room-exam is currently Occupied.")], "")
        result = self.run_agent("own-e", "CLINIC_OWNER", "Give available room details for room-exam", fake)
        self.assertNotIn("update_room", [t["tool"] for t in result["tool_calls_executed"]])
        self.assertEqual(self.row(models.Room, "room-exam").status, "Occupied")

    def test_issue6_intent_classifier(self):
        cls = agent_module._detect_mutation_intent
        self.assertIsNone(cls("Give Available Room Details"))
        self.assertIsNone(cls("Give Task Summary"))
        self.assertIsNone(cls("Show me which rooms are available"))
        self.assertEqual(cls("Change room 102 status to Available"), "room_update")
        self.assertEqual(cls("Create a checklist titled 'Consultation Room Opening Checklist' ... room is clean"), "checklist_create")
        self.assertEqual(cls("Create a task titled 'Treatment Room Readiness Inspection'"), "task_create")
        self.assertEqual(cls("Create the following four rooms in my clinic"), "room_create")
        self.assertEqual(cls("Mark checklist chk-1 as complete"), "checklist_update")

    # --- Issue 7: no fabricated IDs -------------------------------------------------------------------------

    def test_issue7_fabricated_room_ids_are_removed_and_real_ids_reported(self):
        fake = FakeGemini(
            [AIMessage(content="", tool_calls=[
                {"name": "create_room", "id": "1", "args": {"room_number": "01-C", "name": "Consultation Room 01"}},
                {"name": "create_room", "id": "2", "args": {"room_number": "01-T", "name": "Treatment Room 01"}},
            ])],
            "Created: Consultation Room 01 (room-a1b2c3d4) and Treatment Room 01 (room-e5f6g7h8).",
        )
        result = self.run_agent("own-e", "CLINIC_OWNER", "Create the following two rooms: Consultation Room 01, Treatment Room 01", fake)
        db = self.Session()
        real = {r.name: r.id for r in db.query(models.Room).filter(models.Room.tenant_id == T, models.Room.room_number.in_(["01-C", "01-T"]))}
        db.close()
        self.assertEqual(len(real), 2)
        self.assertNotIn("room-a1b2c3d4", result["reply"])
        self.assertNotIn("room-e5f6g7h8", result["reply"])
        for rid in real.values():
            self.assertIn(rid, result["reply"])
        evidence = fake.synthesis_prompts[-1][0].content
        for rid in real.values():
            self.assertIn(rid, evidence)  # both create_room results reach the model, not just the last one

    def test_issue7_ids_from_evidence_are_kept(self):
        executed = [{"tool": "list_tasks", "status": "SUCCESS", "is_read_only": True, "args": {}, "result": {"tasks": [{"task_id": "tsk-kav"}]}}]
        reply = agent_module._ground_resource_ids("Your task tsk-kav is pending.", "Give my tasks", executed, [])
        self.assertEqual(reply, "Your task tsk-kav is pending.")

    # --- Delegation grants view/complete, never Doctor deletion of Owner-created tasks ----------------------------

    def add_owner_delegated_tasks(self):
        db = self.Session()
        db.add_all([
            _task("tsk-own-to-kav", "Owner delegated to nurse", "stf-kav", "CLINIC_OWNER"),
            _task("tsk-mgr-to-kav", "Manager delegated to nurse", "stf-kav", "INVENTORY_MANAGER"),
            _task("tsk-doc-to-kav", "Doctor delegated to nurse", "stf-kav", "ATTENDING_PHYSICIAN", creator_uid="dem-e"),
        ])
        db.commit()
        db.close()

    def test_delegation_assignee_nurse_sees_and_completes_owner_task(self):
        self.add_owner_delegated_tasks()
        hdr = self.h("kav-e")
        task = next(t for t in self.client.get("/api/v1/tasks", headers=hdr).json() if t["id"] == "tsk-own-to-kav")
        self.assertEqual((task["can_complete"], task["can_delete"]), (True, False))
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-own-to-kav", json={"status": "Completed"}, headers=hdr).status_code, 200)
        self.assertEqual(self.row(models.Task, "tsk-own-to-kav").status, "Completed")

    def test_delegation_assignee_doctor_sees_and_completes_but_cannot_delete_owner_task(self):
        hdr = self.h("dem-e")
        task = next(t for t in self.client.get("/api/v1/tasks", headers=hdr).json() if t["id"] == "tsk-dem-own")
        self.assertEqual((task["can_complete"], task["can_delete"]), (True, False))
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-dem-own", headers=hdr).status_code, 403)
        self.assertEqual(self.client.put("/api/v1/tasks/tsk-dem-own", json={"status": "Completed"}, headers=hdr).status_code, 200)
        self.assertIsNotNone(self.row(models.Task, "tsk-dem-own"))

    def test_doctor_cannot_delete_owner_or_manager_created_task_delegated_to_others(self):
        self.add_owner_delegated_tasks()
        hdr = self.h("dem-e")
        for tid in ("tsk-rac-own", "tsk-own-to-kav", "tsk-mgr-to-kav"):
            res = self.client.delete(f"/api/v1/tasks/{tid}", headers=hdr)
            self.assertEqual(res.status_code, 403, (tid, res.text))
            self.assertIn("created by an Owner or Manager", res.json()["detail"])
            self.assertIsNotNone(self.row(models.Task, tid))
        flags = {t["id"]: t for t in self.client.get("/api/v1/tasks", headers=hdr).json()}
        self.assertFalse(flags["tsk-own-to-kav"]["can_delete"])
        self.assertFalse(flags["tsk-rac-own"]["can_delete"])

    def test_doctor_can_still_delete_own_doctor_created_work(self):
        self.add_owner_delegated_tasks()
        hdr = self.h("dem-e")
        self.assertTrue(next(t for t in self.client.get("/api/v1/tasks", headers=hdr).json() if t["id"] == "tsk-doc-to-kav")["can_delete"])
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-doc-to-kav", headers=hdr).status_code, 204)
        # Legacy task without recorded creator: no Doctor owns it, so only Owner/Manager may delete it (policy 2026-10-18)
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-kav", headers=hdr).status_code, 403)
        self.assertIsNotNone(self.row(models.Task, "tsk-kav"))

    def test_self_assigned_delete_restrictions_preserved(self):
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-mgr", headers=self.h("mgr-e")).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-dem-own", headers=self.h("dem-e")).status_code, 403)
        self.assertIsNotNone(self.row(models.Task, "tsk-mgr"))

    def test_owner_and_manager_can_delete_owner_delegated_tasks(self):
        self.add_owner_delegated_tasks()
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-own-to-kav", headers=self.h("own-e")).status_code, 204)
        self.assertEqual(self.client.delete("/api/v1/tasks/tsk-mgr-to-kav", headers=self.h("mgr-e")).status_code, 204)

    # --- Tenant isolation on the changed paths ----------------------------------------------------------------

    def test_changed_paths_do_not_leak_other_tenants(self):
        hdr = self.owner_a_headers()  # tenant-a owner from the shared harness
        ids = {t["id"] for t in self.client.get("/api/v1/tasks", headers=hdr).json()}
        self.assertFalse(any(i.startswith("tsk-") and i in ("tsk-dem-own", "tsk-kav") for i in ids))
        self.assertEqual(self.client.get("/api/v1/dashboard/summary", headers=hdr).json()["tasks_total"], len(ids))
        self.assertEqual(self.client.put("/api/v1/checklists/chk-kav-own", json={"title": "x"}, headers=hdr).status_code, 404)


if __name__ == "__main__":
    unittest.main()
