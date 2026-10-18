"""Authenticated Tool Gateway, approval, RBAC, and audit regressions."""

from practicare_phase0_harness import PractiCareIsolatedTestCase, models
from ai.context import SecurityContext
from ai.gateway import gateway


class PractiCareAuthorizationIntegrationTests(PractiCareIsolatedTestCase):
    def test_custom_headers_do_not_authenticate_or_override_identity(self):
        spoofed = {"x-user-id": "owner-a", "x-tenant-id": "tenant-a", "x-user-role": "CLINIC_OWNER"}
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=spoofed).status_code, 401)
        headers = self.nurse_a_headers() | {"x-user-id": "owner-b", "x-tenant-id": "tenant-b", "x-user-role": "CLINIC_OWNER"}
        response = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["id"], response.json()["tenant_id"], response.json()["role"]), ("nurse-a", "tenant-a", "NURSE_STAFF"))

    def test_rest_and_gateway_apply_consistent_delete_rbac(self):
        self.assertEqual(self.client.delete("/api/v1/tasks/task-a", headers=self.nurse_a_headers()).status_code, 403)
        db = self.Session()
        result = gateway.execute(
            "delete_clinical_checklist", {"checklist_id": "check-a"},
            SecurityContext.create("tenant-a", "nurse-a", "NURSE_STAFF"), db,
        )
        self.assertEqual(result["error"], "FORBIDDEN")
        self.assertIsNotNone(db.query(models.Checklist).filter_by(id="check-a").first())
        db.close()

    def test_approval_ownership_execution_replay_and_persistent_audit(self):
        db = self.Session()
        pending = gateway.execute(
            "delete_clinical_checklist", {"checklist_id": "check-a"},
            SecurityContext.create("tenant-a", "owner-a", "CLINIC_OWNER"), db,
        )
        approval_id = pending["approval_id"]
        db.close()
        self.assertEqual(self.client.post("/api/v1/ai/approve", headers=self.owner_b_headers(), json={"approval_id": approval_id, "action": "approve"}).status_code, 400)
        self.assertEqual(self.client.post("/api/v1/ai/approve", headers=self.owner_a2_headers(), json={"approval_id": approval_id, "action": "approve"}).status_code, 400)
        approved = self.client.post("/api/v1/ai/approve", headers=self.owner_a_headers(), json={"approval_id": approval_id, "action": "approve"})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "EXECUTED")
        self.assertEqual(self.client.post("/api/v1/ai/approve", headers=self.owner_a_headers(), json={"approval_id": approval_id, "action": "approve"}).status_code, 400)
        db = self.Session()
        self.assertEqual(db.query(models.AIPendingApproval).filter_by(id=approval_id).one().status, "EXECUTED")
        self.assertIsNone(db.query(models.Checklist).filter_by(id="check-a").first())
        self.assertGreater(db.query(models.AIAuditEvent).filter_by(tenant_id="tenant-a").count(), 0)
        db.close()
        logs = self.client.get("/api/v1/ai/audit", headers=self.owner_a_headers())
        self.assertEqual(logs.status_code, 200, logs.text)
        self.assertTrue(logs.json()["logs"])
        self.assertTrue(all(row["tenant_id"] == "tenant-a" for row in logs.json()["logs"]))
        self.assertEqual(self.client.get("/api/v1/ai/audit", headers=self.nurse_a_headers()).status_code, 403)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
