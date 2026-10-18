"""Deny-by-default discovery and invocation, tenant isolation, safe errors, audit and redaction,
over real Streamable HTTP (design §6 rows 19-29)."""

from __future__ import annotations

import json
import unittest

from _live_server import LiveServer
from _security_fixtures import CLINICAL_ROLES, call_body, make_world, post, rpc

ECHO = "testapp_echo_context"
OWNER_ONLY = "testapp_get_owner_summary"
OTHER_APP_TOOL = "otherapp_echo_context"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "authz", "version": "0"}},
}


class LiveAuthorizationTestCase(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = make_world()
        cls.server = LiveServer(registry=cls.world.registry, adapters=cls.world.adapter_list).__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def setUp(self) -> None:
        for adapter in self.world.adapters.values():
            adapter.calls.clear()

    async def list_tools(self, **claims) -> dict:
        t = self.world.testapp
        response = await post(self.server.mcp_url, rpc("tools/list"), t.headers(t.assertion(**claims)))
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def call(self, name: str, arguments: dict | None = None, *, extra_headers: dict | None = None, body=None, **claims):
        t = self.world.testapp
        assertion = t.assertion("tools/call", name, **claims)
        response = await post(
            self.server.mcp_url, body or call_body(name, arguments), t.headers(assertion, **(extra_headers or {}))
        )
        self.assertEqual(response.status_code, 200)
        return response.json(), response.text, assertion

    @property
    def adapter_calls(self) -> list:
        return self.world.adapters["testapp"].calls + self.world.adapters["otherapp"].calls


class DiscoveryTests(LiveAuthorizationTestCase):
    async def test_discovery_per_role(self) -> None:
        expected = {
            "CLINIC_OWNER": [ECHO, OWNER_ONLY],
            "INVENTORY_MANAGER": [ECHO],
            "ATTENDING_PHYSICIAN": [ECHO],
            "NURSE_STAFF": [ECHO],
            "CLINICAL_AUDITOR": [],
            "JANITOR": [],
            "NURSE": [],  # role aliases are not canonical
            "DOCTOR": [],
            "OWNER": [],
        }
        for role, tools in expected.items():
            with self.subTest(role=role):
                body = await self.list_tools(role=role)
                self.assertEqual(sorted(tool["name"] for tool in body["result"]["tools"]), sorted(tools))

    async def test_tools_of_other_apps_never_listed(self) -> None:
        body = await self.list_tools(role="CLINIC_OWNER")
        self.assertNotIn(OTHER_APP_TOOL, json.dumps(body))
        o = self.world.otherapp
        response = await post(self.server.mcp_url, rpc("tools/list"), o.headers(o.assertion(role="CLINIC_OWNER")))
        self.assertEqual([tool["name"] for tool in response.json()["result"]["tools"]], [OTHER_APP_TOOL])

    async def test_no_anonymous_discovery(self) -> None:
        response = await post(self.server.mcp_url, rpc("tools/list"), self.world.testapp.headers())
        body = response.json()
        self.assertEqual(body["error"]["code"], -32001)
        self.assertEqual(body["error"]["data"]["error"], "UNAUTHENTICATED")
        self.assertNotIn(ECHO, response.text)

    async def test_listed_tools_contain_no_identity_or_credentials(self) -> None:
        t = self.world.testapp
        assertion = t.assertion(role="CLINIC_OWNER")
        response = await post(self.server.mcp_url, rpc("tools/list"), t.headers(assertion))
        for tool in response.json()["result"]["tools"]:
            self.assertFalse(tool["inputSchema"].get("additionalProperties", True))
            self.assertFalse({"tenant_id", "user_id", "role", "permissions"} & set(tool["inputSchema"]["properties"]))
            self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertNotIn(t.token, response.text)
        self.assertNotIn(assertion, response.text)
        self.assertNotIn("X-MCP-User-Assertion", response.text)

    async def test_assertion_of_other_app_with_this_apps_token(self) -> None:
        t, o = self.world.testapp, self.world.otherapp
        response = await post(self.server.mcp_url, rpc("tools/list"), t.headers(o.assertion(role="CLINIC_OWNER")))
        self.assertEqual(response.json()["error"]["data"]["error"], "UNAUTHENTICATED")

    async def test_initialize_and_notifications_do_not_consume_the_assertion(self) -> None:
        t = self.world.testapp
        headers = t.headers(t.assertion())
        init = await post(self.server.mcp_url, INITIALIZE, headers)
        self.assertEqual(init.status_code, 200)
        note = await post(self.server.mcp_url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, headers)
        self.assertEqual(note.status_code, 202)
        ping = await post(self.server.mcp_url, rpc("ping", request_id=5), headers)
        self.assertEqual(ping.json()["result"], {})
        listed = await post(self.server.mcp_url, rpc("tools/list"), headers)
        self.assertIn("result", listed.json())


class InvocationTests(LiveAuthorizationTestCase):
    async def test_allowed_call_receives_only_verified_identity(self) -> None:
        body, _, assertion = await self.call(
            ECHO, {"message": "hi", "limit": 3}, sub="usr-77", tid="tenant-002", role="ATTENDING_PHYSICIAN", cid="cid-verified-1"
        )
        result = body["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(
            result["structuredContent"],
            {
                "tool": ECHO,
                "app_id": "testapp",
                "user_id": "usr-77",
                "tenant_id": "tenant-002",
                "role": "ATTENDING_PHYSICIAN",
                "correlation_id": "cid-verified-1",
                "arguments": {"message": "hi", "limit": 3},
            },
        )
        (arguments, context), = self.world.adapters["testapp"].calls
        self.assertEqual(context.assertion, assertion)  # forwarded for downstream re-verification
        self.assertEqual(arguments, {"message": "hi", "limit": 3})

    async def test_hidden_forbidden_and_unknown_tools_are_indistinguishable(self) -> None:
        cases = [
            (ECHO, {"role": "CLINICAL_AUDITOR"}),
            (OWNER_ONLY, {"role": "NURSE_STAFF"}),
            (OWNER_ONLY, {"role": "INVENTORY_MANAGER"}),
            (OTHER_APP_TOOL, {"role": "CLINIC_OWNER"}),
            ("testapp_delete_everything", {"role": "CLINIC_OWNER"}),
            (ECHO, {"role": "NURSE"}),
        ]
        errors = []
        for name, claims in cases:
            with self.subTest(name=name, **claims):
                body, _, _ = await self.call(name, {}, **claims)
                error = body["error"]
                self.assertEqual((error["code"], error["message"], error["data"]["error"]), (-32602, "Unknown tool", "NOT_FOUND"))
                error["data"].pop("correlation_id")
                errors.append(error)
        self.assertTrue(all(error == errors[0] for error in errors))
        self.assertEqual(self.adapter_calls, [])

    async def test_identity_arguments_rejected_cross_tenant(self) -> None:
        for field in ("tenant_id", "tid", "user_id", "role", "permissions", "tenantId"):
            with self.subTest(field=field):
                body, text, _ = await self.call(ECHO, {field: "tenant-B"}, tid="tenant-A")
                self.assertEqual(body["error"]["data"]["error"], "VALIDATION_ERROR")
                self.assertNotIn("tenant-B", text)
        self.assertEqual(self.adapter_calls, [])

    async def test_tenant_headers_and_forged_body_fields_ignored(self) -> None:
        body = call_body(ECHO, {"limit": 1})
        body["params"].update({"tenant_id": "tenant-B", "user_id": "usr-evil", "role": "CLINIC_OWNER"})
        body["params"]["_meta"] = {"tenant_id": "tenant-B", "role": "CLINIC_OWNER"}
        result, _, _ = await self.call(
            ECHO,
            body=body,
            extra_headers={"X-Tenant-ID": "tenant-B", "X-User-Role": "CLINIC_OWNER", "X-User-ID": "usr-evil"},
            tid="tenant-A",
            role="NURSE_STAFF",
        )
        content = result["result"]["structuredContent"]
        self.assertEqual((content["tenant_id"], content["role"], content["user_id"]), ("tenant-A", "NURSE_STAFF", "usr-0001"))
        (_, context), = self.world.adapters["testapp"].calls
        self.assertEqual((context.tenant_id, context.role), ("tenant-A", "NURSE_STAFF"))

    async def test_schema_violations_do_not_echo_values(self) -> None:
        for arguments, pointer in (
            ({"limit": 999}, "/limit"),
            ({"message": 12345}, "/message"),
            ({"message": "secret-arg-value" * 20}, "/message"),
        ):
            with self.subTest(pointer=pointer):
                body, text, _ = await self.call(ECHO, arguments)
                data = body["error"]["data"]
                self.assertEqual((data["error"], data["pointer"]), ("VALIDATION_ERROR", pointer))
                self.assertNotIn("999", text)
                self.assertNotIn("12345", text)
                self.assertNotIn("secret-arg-value", text)
        self.assertEqual(self.adapter_calls, [])

    async def test_adapter_failures_are_structured_without_details(self) -> None:
        for message, code in (("adapter-timeout", "TIMEOUT"), ("adapter-crash", "UPSTREAM_ERROR"), ("adapter-bad-output", "UPSTREAM_ERROR")):
            with self.subTest(message=message):
                body, text, _ = await self.call(ECHO, {"message": message}, cid="cid-failure-1")
                result = body["result"]
                self.assertTrue(result["isError"])
                self.assertEqual(result["structuredContent"], {"error": code, "correlation_id": "cid-failure-1"})
                self.assertNotIn("secret-detail-xyz", text)
                self.assertNotIn("Traceback", text)

    async def test_call_responses_contain_no_credentials(self) -> None:
        body, text, assertion = await self.call(ECHO, {"limit": 1})
        self.assertNotIn(assertion, text)
        self.assertNotIn(self.world.testapp.token, text)
        self.assertNotIn(assertion.split(".")[2], text)


class AuditTests(LiveAuthorizationTestCase):
    async def test_every_decision_is_audited_and_redacted(self) -> None:
        t = self.world.testapp
        with self.assertLogs("shared_mcp_server.audit", level="INFO") as logs:
            await self.list_tools(role="CLINIC_OWNER", cid="cid-audit-list")
            await self.call(ECHO, {"message": "secret-arg-value nurse@example.com"}, cid="cid-audit-ok")
            await self.call(OWNER_ONLY, {}, role="NURSE_STAFF", cid="cid-audit-hidden")
            await self.call(ECHO, {"limit": 999}, cid="cid-audit-invalid")
            await self.call(ECHO, {"message": "adapter-timeout"}, cid="cid-audit-adapter")
            await post(self.server.mcp_url, call_body(ECHO), t.headers(t.assertion("tools/call", ECHO, aud="wrong", sub="usr-unverified")))
        records = [json.loads(record.getMessage()) for record in logs.records]
        by_cid = {record.get("correlation_id"): record for record in records}

        listed = by_cid["cid-audit-list"]
        self.assertEqual((listed["event"], listed["decision"], listed["app"]), ("mcp.tools.list", "ALLOWED", "testapp"))
        self.assertEqual(listed["returned_tools"], [ECHO, OWNER_ONLY])
        ok = by_cid["cid-audit-ok"]
        self.assertEqual((ok["event"], ok["tool"], ok["decision"], ok["outcome"]), ("mcp.tools.call", ECHO, "ALLOWED", "SUCCESS"))
        self.assertEqual((ok["tenant"], ok["user"], ok["role"], ok["arg_keys"]), ("tenant-001", "usr-0001", "NURSE_STAFF", ["message"]))
        self.assertEqual((by_cid["cid-audit-hidden"]["decision"], by_cid["cid-audit-hidden"]["reason"]), ("DENIED", "UNKNOWN_TOOL"))
        self.assertEqual(by_cid["cid-audit-invalid"]["reason"], "VALIDATION_ERROR")
        self.assertEqual((by_cid["cid-audit-adapter"]["reason"], by_cid["cid-audit-adapter"]["error_code"]), ("ADAPTER_ERROR", "TIMEOUT"))
        denied = [r for r in records if r.get("reason") == "WRONG_AUDIENCE"]
        self.assertEqual(len(denied), 1)
        self.assertTrue(denied[0]["correlation_id"].startswith("srv-"))
        self.assertNotIn("user", denied[0])  # claims of unverified assertions are never logged

        joined = "\n".join(logs.output)
        for forbidden in ("secret-arg-value", "nurse@example.com", "usr-unverified", t.token, "eyJ"):
            self.assertNotIn(forbidden, joined)
        for record in records:
            self.assertIn("ts", record)


if __name__ == "__main__":
    unittest.main()
