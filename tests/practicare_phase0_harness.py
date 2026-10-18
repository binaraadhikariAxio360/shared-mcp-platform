"""Shared, isolated FastAPI harness for PractiCare Phase 0 integration tests."""

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SESSION_SECRET_KEY", "phase0-integration-test-session-secret-value")
os.environ.setdefault("AI_AGENT_MODE", "deterministic")

BACKEND_DIR = Path(__file__).resolve().parents[1] / "apps" / "practicare" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import get_db, hash_password


class PractiCareIsolatedTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
        main._invitation_attempt_log.clear()
        db = self.Session()
        for table in reversed(models.Base.metadata.sorted_tables):
            db.execute(table.delete())

        practice_a = models.Practice(id="practice-a", name="Clinic A", location="A", tenant_id="tenant-a")
        practice_b = models.Practice(id="practice-b", name="Clinic B", location="B", tenant_id="tenant-b")
        users = [
            models.User(id="owner-a", email="owner-a@test.local", password_hash=hash_password("OwnerPass1!"), full_name="Owner A", role="CLINIC_OWNER", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.User(id="owner-a2", email="owner-a2@test.local", password_hash=hash_password("OwnerPass1!"), full_name="Owner A2", role="CLINIC_OWNER", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.User(id="nurse-a", email="nurse-a@test.local", password_hash=hash_password("NursePass1!"), full_name="Nurse A", role="NURSE_STAFF", tenant_id="tenant-a", company_name="Clinic A", membership_status="APPROVED", is_active=True),
            models.User(id="owner-b", email="owner-b@test.local", password_hash=hash_password("OwnerPass1!"), full_name="Owner B", role="CLINIC_OWNER", tenant_id="tenant-b", company_name="Clinic B", membership_status="APPROVED", is_active=True),
        ]
        staff = [
            models.Staff(id="staff-owner-a", name="Owner A", role="Doctor", user_id="owner-a", practice_id="practice-a", tenant_id="tenant-a"),
            models.Staff(id="staff-nurse-a", name="Nurse A", role="Nurse", user_id="nurse-a", practice_id="practice-a", tenant_id="tenant-a"),
        ]
        records = [
            models.Room(id="room-a", room_number="A1", name="A Room", practice_id="practice-a", tenant_id="tenant-a"),
            models.Room(id="room-b", room_number="B1", name="B Room", practice_id="practice-b", tenant_id="tenant-b"),
            models.Task(id="task-a", title="Protected task", due_date="2026-10-17", practice_id="practice-a", tenant_id="tenant-a"),
            models.Checklist(id="check-a", title="Protected checklist", practice_id="practice-a", tenant_id="tenant-a"),
        ]
        db.add_all([practice_a, practice_b, *users, *staff, *records])
        db.commit()
        db.close()

    def login_headers(self, email: str, password: str):
        response = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def owner_a_headers(self):
        return self.login_headers("owner-a@test.local", "OwnerPass1!")

    def owner_a2_headers(self):
        return self.login_headers("owner-a2@test.local", "OwnerPass1!")

    def owner_b_headers(self):
        return self.login_headers("owner-b@test.local", "OwnerPass1!")

    def nurse_a_headers(self):
        return self.login_headers("nurse-a@test.local", "NursePass1!")
