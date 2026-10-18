"""Authenticated, isolated PractiCare API workflow regressions."""

from practicare_phase0_harness import PractiCareIsolatedTestCase, models


class PractiCareCrudIntegrationTests(PractiCareIsolatedTestCase):
    def test_company_registration_ignores_requested_tenant_and_role(self):
        response = self.client.post("/api/v1/auth/register", json={
            "email": "new-owner@test.local", "password": "NewOwnerPass1!", "full_name": "New Owner",
            "company_name": "New Clinic", "tenant_id": "tenant-b", "role": "SYSTEM_ADMIN",
        })
        self.assertEqual(response.status_code, 200, response.text)
        user = response.json()["user"]
        self.assertEqual(user["role"], "CLINIC_OWNER")
        self.assertNotEqual(user["tenant_id"], "tenant-b")
        me = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["tenant_id"], user["tenant_id"])

    def test_login_and_authenticated_task_mutation(self):
        response = self.client.post("/api/v1/tasks", headers=self.owner_a_headers(), json={
            "title": "Authenticated task", "due_date": "2026-10-18", "room_id": "room-a", "practice_id": "practice-b",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["tenant_id"], "tenant-a")
        self.assertEqual(response.json()["practice_id"], "practice-a")

    def test_invitation_join_pending_approval_and_login(self):
        invitation = self.client.post("/api/v1/company/invitations", headers=self.owner_a_headers(), json={
            "role": "NURSE_STAFF", "max_uses": 1, "expires_in_days": 2,
        })
        self.assertEqual(invitation.status_code, 200, invitation.text)
        joined = self.client.post("/api/v1/auth/join", json={
            "email": "joiner@test.local", "password": "JoinerPass1!", "full_name": "Joiner One",
            "invitation_code": invitation.json()["code"],
        })
        self.assertEqual(joined.status_code, 200, joined.text)
        self.assertEqual(joined.json()["tenant_id"], "tenant-a")
        self.assertEqual(joined.json()["user"]["role"], "NURSE_STAFF")
        self.assertEqual(joined.json()["membership_status"], "PENDING")
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"email": "joiner@test.local", "password": "JoinerPass1!"}).status_code, 403)
        approved = self.client.post(
            f"/api/v1/company/pending-members/{joined.json()['user_id']}/action",
            headers=self.owner_a_headers(), json={"action": "APPROVE", "role": "NURSE_STAFF"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(self.client.post("/api/v1/auth/login", json={"email": "joiner@test.local", "password": "JoinerPass1!"}).status_code, 200)

    def test_cross_tenant_records_and_relationships_are_hidden(self):
        self.assertEqual(self.client.get("/api/v1/tasks/task-a", headers=self.owner_b_headers()).status_code, 404)
        injected = self.client.post("/api/v1/tasks", headers=self.owner_a_headers(), json={
            "title": "Cross tenant relationship", "due_date": "2026-10-18", "room_id": "room-b",
        })
        self.assertEqual(injected.status_code, 404)
        db = self.Session()
        self.assertEqual(db.query(models.Task).filter_by(title="Cross tenant relationship").count(), 0)
        db.close()


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
