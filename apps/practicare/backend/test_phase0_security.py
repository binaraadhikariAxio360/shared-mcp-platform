"""Isolated Phase 0 security regressions for PractiCare."""

import os
import hashlib
import unittest

os.environ.setdefault("SESSION_SECRET_KEY", "phase0-test-only-session-secret-value")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from ai.context import SecurityContext
from ai.gateway import gateway
from database import get_db, hash_password
from security import create_access_token


class Phase0SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)
        models.Base.metadata.create_all(cls.engine)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        main.app.dependency_overrides.clear()
        models.Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())

        self.practice_a = models.Practice(
            id="practice-a", name="Clinic A", location="A", tenant_id="tenant-a"
        )
        self.practice_b = models.Practice(
            id="practice-b", name="Clinic B", location="B", tenant_id="tenant-b"
        )
        users = [
            models.User(id="owner-a", email="owner-a@test.local", password_hash=hash_password("pw"), full_name="Owner A", role="CLINIC_OWNER", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.User(id="owner-a2", email="owner-a2@test.local", password_hash=hash_password("pw"), full_name="Owner A2", role="CLINIC_OWNER", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.User(id="nurse-a", email="nurse-a@test.local", password_hash=hash_password("pw"), full_name="Nurse A", role="NURSE_STAFF", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.User(id="owner-b", email="owner-b@test.local", password_hash=hash_password("pw"), full_name="Owner B", role="CLINIC_OWNER", tenant_id="tenant-b", company_name="Clinic B", membership_status="APPROVED", is_active=True),
        ]
        self.room_a = models.Room(id="room-a", room_number="A1", name="A Room", practice_id="practice-a", tenant_id="tenant-a")
        self.room_b = models.Room(id="room-b", room_number="B1", name="B Room", practice_id="practice-b", tenant_id="tenant-b")
        self.task_a = models.Task(id="task-a", title="Protected task", due_date="2026-10-17", practice_id="practice-a", tenant_id="tenant-a")
        self.checklist_a = models.Checklist(id="check-a", title="Protected checklist", practice_id="practice-a", tenant_id="tenant-a")
        db.add_all([self.practice_a, self.practice_b, *users, self.room_a, self.room_b, self.task_a, self.checklist_a])
        db.commit()
        db.close()

    @staticmethod
    def auth(user_id, tenant_id, role):
        token = create_access_token(user_id=user_id, tenant_id=tenant_id, role=role)
        return {"Authorization": f"Bearer {token}"}

    def test_custom_identity_headers_cannot_authenticate_or_override_token(self):
        spoof = {"x-user-id": "owner-a", "x-tenant-id": "tenant-a", "x-user-role": "CLINIC_OWNER"}
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=spoof).status_code, 401)

        headers = self.auth("nurse-a", "tenant-a", "NURSE_STAFF") | {
            "x-user-id": "owner-b", "x-tenant-id": "tenant-b", "x-user-role": "CLINIC_OWNER"
        }
        response = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "nurse-a")
        self.assertEqual(response.json()["role"], "NURSE_STAFF")
        self.assertEqual(response.json()["tenant_id"], "tenant-a")

    def test_legacy_registration_cannot_choose_tenant_or_role(self):
        response = self.client.post("/api/v1/auth/register", json={
            "email": "new-owner@test.local", "password": "pw", "full_name": "New Owner",
            "company_name": "New Clinic", "tenant_id": "tenant-b", "role": "SYSTEM_ADMIN",
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()["user"]
        self.assertEqual(body["role"], "CLINIC_OWNER")
        self.assertNotEqual(body["tenant_id"], "tenant-b")

    def test_legacy_password_is_upgraded_after_successful_login(self):
        db = self.Session()
        user = db.query(models.User).filter_by(id="owner-a").one()
        user.password_hash = hashlib.sha256(b"axio360_secure_salt:pw").hexdigest()
        db.commit()
        db.close()

        response = self.client.post("/api/v1/auth/login", json={"email": "owner-a@test.local", "password": "pw"})
        self.assertEqual(response.status_code, 200, response.text)
        db = self.Session()
        self.assertTrue(db.query(models.User).filter_by(id="owner-a").one().password_hash.startswith("pbkdf2_sha256$"))
        db.close()

    def test_cross_tenant_reads_and_relationship_writes_are_rejected(self):
        headers = self.auth("owner-a", "tenant-a", "CLINIC_OWNER")
        self.assertEqual(self.client.get("/api/v1/tasks/task-a", headers=self.auth("owner-b", "tenant-b", "CLINIC_OWNER")).status_code, 404)
        response = self.client.post("/api/v1/tasks", headers=headers, json={
            "title": "Injected room", "due_date": "2026-10-18", "room_id": "room-b",
            "practice_id": "practice-b",
        })
        self.assertEqual(response.status_code, 404, response.text)
        db = self.Session()
        self.assertEqual(db.query(models.Task).filter(models.Task.title == "Injected room").count(), 0)
        db.close()

    def test_rest_and_tool_gateway_both_reject_unauthorized_delete(self):
        headers = self.auth("nurse-a", "tenant-a", "NURSE_STAFF")
        self.assertEqual(self.client.delete("/api/v1/tasks/task-a", headers=headers).status_code, 403)
        db = self.Session()
        context = SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF")
        result = gateway.execute("delete_clinical_checklist", {"checklist_id": "check-a"}, context, db)
        self.assertEqual(result["error"], "FORBIDDEN")
        self.assertIsNotNone(db.query(models.Checklist).filter_by(id="check-a").first())
        db.close()

    def test_approval_is_bound_to_user_tenant_role_action_and_single_execution(self):
        db = self.Session()
        context = SecurityContext.create("tenant-a", "owner-a", "CLINIC_OWNER")
        pending = gateway.execute("delete_clinical_checklist", {"checklist_id": "check-a"}, context, db)
        approval_id = pending["approval_id"]
        db.close()

        wrong_tenant = self.client.post("/api/v1/ai/approve", headers=self.auth("owner-b", "tenant-b", "CLINIC_OWNER"), json={"approval_id": approval_id, "action": "approve"})
        self.assertEqual(wrong_tenant.status_code, 400)
        wrong_user = self.client.post("/api/v1/ai/approve", headers=self.auth("owner-a2", "tenant-a", "CLINIC_OWNER"), json={"approval_id": approval_id, "action": "approve"})
        self.assertEqual(wrong_user.status_code, 400)
        invalid_action = self.client.post("/api/v1/ai/approve", headers=self.auth("owner-a", "tenant-a", "CLINIC_OWNER"), json={"approval_id": approval_id, "action": "execute"})
        self.assertEqual(invalid_action.status_code, 400)

        approved = self.client.post("/api/v1/ai/approve", headers=self.auth("owner-a", "tenant-a", "CLINIC_OWNER"), json={"approval_id": approval_id, "action": "approve"})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertTrue(approved.json()["success"])
        self.assertEqual(approved.json()["status"], "EXECUTED")

        replay = self.client.post("/api/v1/ai/approve", headers=self.auth("owner-a", "tenant-a", "CLINIC_OWNER"), json={"approval_id": approval_id, "action": "approve"})
        self.assertEqual(replay.status_code, 400)
        db = self.Session()
        self.assertIsNone(db.query(models.Checklist).filter_by(id="check-a").first())
        approval = db.query(models.AIPendingApproval).filter_by(id=approval_id).one()
        self.assertEqual(approval.status, "EXECUTED")
        self.assertGreater(db.query(models.AIAuditEvent).count(), 0)
        db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
