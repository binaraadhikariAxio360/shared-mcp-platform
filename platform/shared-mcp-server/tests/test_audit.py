from __future__ import annotations

import json
import unittest

from shared_mcp_server.audit import REDACTED, arg_keys, audit_event, redact

JWT = "eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiJ1c3ItMSIsInRpZCI6InRlbmFudC0wMDEifQ.c2lnbmF0dXJlLXZhbHVl"
SESSION = "pcsess.dXNyLTE.MTcwMDAwMDAwMA.abcdef0123456789"


class RedactionTests(unittest.TestCase):
    def test_sensitive_keys_masked_at_any_depth(self) -> None:
        record = redact(
            {
                "Authorization": "Bearer abc",
                "headers": {"X-MCP-User-Assertion": "x", "cookie": "y", "x-api-key": "z"},
                "client_token": "t",
                "SESSION_SECRET_KEY": "s",
                "password": "p",
                "private_key": "k",
                "items": [{"refresh_token": "r", "name": "Gloves"}],
            }
        )
        self.assertEqual(record["Authorization"], REDACTED)
        self.assertEqual(record["headers"], {"X-MCP-User-Assertion": REDACTED, "cookie": REDACTED, "x-api-key": REDACTED})
        for key in ("client_token", "SESSION_SECRET_KEY", "password", "private_key"):
            self.assertEqual(record[key], REDACTED, key)
        self.assertEqual(record["items"], [{"refresh_token": REDACTED, "name": "Gloves"}])

    def test_token_shaped_values_masked_under_harmless_keys(self) -> None:
        record = redact(
            {
                "detail": f"upstream said Bearer {JWT} for {SESSION}",
                "note": JWT,
                "approval": "appr-0123456789abcdef",
                "pem": "-----BEGIN PRIVATE KEY-----\nMC4CAQ...",
            }
        )
        serialized = json.dumps(record)
        for secret in (JWT, SESSION, "appr-0123456789abcdef", "BEGIN PRIVATE KEY"):
            self.assertNotIn(secret, serialized)
        self.assertTrue(record["detail"].startswith("upstream said "))

    def test_service_tokens_and_emails_masked(self) -> None:
        token = "mcpsvc_" + "A1b2_" * 8 + "xyz"
        record = redact({"detail": f"sent {token}", "user": "dr.jane.doe@clinic.example.org", "note": "ok"})
        serialized = json.dumps(record)
        self.assertNotIn(token, serialized)
        self.assertNotIn("jane.doe", serialized)
        self.assertEqual(record["note"], "ok")

    def test_token_id_is_kept_but_its_value_still_scanned(self) -> None:
        self.assertEqual(redact({"token_id": "practicare-svc-1"}), {"token_id": "practicare-svc-1"})
        self.assertEqual(redact({"token_id": "mcpsvc_abcdef"}), {"token_id": REDACTED})
        self.assertEqual(redact({"client_token": "x"}), {"client_token": REDACTED})

    def test_arg_keys_names_only(self) -> None:
        self.assertEqual(arg_keys({"limit": 5, "message": "secret"}), ["limit", "message"])
        self.assertEqual(arg_keys(None), [])
        self.assertEqual(len(arg_keys({f"k{i}": i for i in range(100)})), 32)
        self.assertEqual(arg_keys({"x" * 200: 1}), ["x" * 64])

    def test_safe_values_unchanged(self) -> None:
        values = {"tool": "practicare_list_tasks", "tenant": "tenant-001", "latency_ms": 12.5, "ok": True, "n": None}
        self.assertEqual(redact(values), values)

    def test_long_strings_and_deep_nesting_truncated(self) -> None:
        self.assertTrue(redact("a" * 2000).endswith("...[TRUNCATED]"))
        self.assertLessEqual(len(redact("a" * 2000)), 512 + len("...[TRUNCATED]"))
        nested: dict = {"v": 1}
        for _ in range(10):
            nested = {"n": nested}
        self.assertIn("[TRUNCATED]", json.dumps(redact(nested)))

    def test_non_json_values_stringified(self) -> None:
        self.assertEqual(sorted(redact({"s": {1, 2}})["s"]), [1, 2])
        self.assertEqual(redact(Exception(f"failed with {SESSION}")), f"failed with {REDACTED}")


class AuditEventTests(unittest.TestCase):
    def test_emits_one_redacted_json_line(self) -> None:
        with self.assertLogs("shared_mcp_server.audit", level="INFO") as captured:
            record = audit_event(
                "tool.call",
                cid="aud-1",
                app="practicare",
                tool="practicare_list_tasks",
                decision="ALLOWED",
                authorization=f"Bearer {JWT}",
                detail={"assertion": JWT, "message": f"token {SESSION}"},
            )
        self.assertEqual(len(captured.output), 1)
        line = captured.records[0].getMessage()
        self.assertEqual(json.loads(line), record)
        self.assertEqual(record["event"], "tool.call")
        self.assertIn("ts", record)
        self.assertEqual(record["authorization"], REDACTED)
        self.assertNotIn(JWT, line)
        self.assertNotIn(SESSION, line)


if __name__ == "__main__":
    unittest.main()
