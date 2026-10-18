"""Hop A: every /mcp request must authenticate the calling application (design §6 rows 1-4)."""

from __future__ import annotations

import json
import time
import unittest
from datetime import timedelta

import httpx2

from _live_server import LiveServer
from _security_fixtures import (
    ACCEPT,
    PINNED,
    AppCreds,
    make_world,
    new_service_token,
    post,
    rpc,
    utc,
)
from shared_mcp_server.auth.service_tokens import ServiceTokenVerifier, hash_token
from shared_mcp_server.errors import McpSecurityError
from shared_mcp_server.registry import build_registry

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": PINNED, "capabilities": {}, "clientInfo": {"name": "auth-test", "version": "0"}},
}


def base_headers(**extra: str) -> dict[str, str]:
    return {"Accept": ACCEPT, "Content-Type": "application/json", "MCP-Protocol-Version": PINNED, **extra}


class ServiceTokenVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = AppCreds("testapp")
        self.now = time.time()
        self.verifier = ServiceTokenVerifier(build_registry([self.app.registration()]).apps.values(), clock=lambda: self.now)

    def reason(self, values: list[str]) -> str:
        with self.assertRaises(McpSecurityError) as caught:
            self.verifier.verify(values)
        self.assertEqual(caught.exception.code, "UNAUTHENTICATED")
        return caught.exception.reason

    def test_valid_token(self) -> None:
        caller = self.verifier.verify([f"Bearer {self.app.token}"])
        self.assertEqual((caller.app_id, caller.token_id), ("testapp", "testapp-svc-1"))
        self.assertEqual(self.verifier.verify([f"bearer {self.app.token}"]).app_id, "testapp")

    def test_missing_and_malformed(self) -> None:
        self.assertEqual(self.reason([]), "MISSING_TOKEN")
        for value in (
            "",
            self.app.token,  # no scheme
            f"Basic {self.app.token}",
            f"Bearer  {self.app.token}",
            f"Bearer {self.app.token} extra",
            f"Bearer {self.app.token.upper()}",  # prefix must be lowercase 'mcpsvc_'
            f"Bearer {self.app.token[:-1]}",
            "Bearer mcpsvc_",
        ):
            with self.subTest(value=value[:20]):
                self.assertEqual(self.reason([value]), "INVALID_TOKEN")

    def test_unknown_token_and_duplicate_headers(self) -> None:
        self.assertEqual(self.reason([f"Bearer {new_service_token()}"]), "INVALID_TOKEN")
        self.assertEqual(self.reason([f"Bearer {self.app.token}", f"Bearer {self.app.token}"]), "INVALID_TOKEN")

    def test_validity_window(self) -> None:
        app = AppCreds("testapp")
        credential = app.credential(not_before=utc(timedelta(hours=1)), not_after=utc(timedelta(days=2)))
        verifier = ServiceTokenVerifier(build_registry([app.registration((credential,))]).apps.values())
        with self.assertRaises(McpSecurityError) as caught:
            verifier.verify([f"Bearer {app.token}"])
        self.assertEqual(caught.exception.reason, "TOKEN_NOT_YET_VALID")

        expired = app.credential(not_after=utc(timedelta(seconds=-1)))
        verifier = ServiceTokenVerifier(build_registry([app.registration((expired,))]).apps.values())
        with self.assertRaises(McpSecurityError) as caught:
            verifier.verify([f"Bearer {app.token}"])
        self.assertEqual(caught.exception.reason, "EXPIRED_TOKEN")

    def test_expiry_follows_the_clock(self) -> None:
        not_after = utc(timedelta(minutes=5))
        app = AppCreds("testapp")
        clock = {"now": time.time()}
        verifier = ServiceTokenVerifier(
            build_registry([app.registration((app.credential(not_after=not_after),))]).apps.values(),
            clock=lambda: clock["now"],
        )
        self.assertEqual(verifier.verify([f"Bearer {app.token}"]).app_id, "testapp")
        clock["now"] = not_after.timestamp()
        with self.assertRaises(McpSecurityError):
            verifier.verify([f"Bearer {app.token}"])

    def test_overlapping_tokens_for_rotation(self) -> None:
        app = AppCreds("testapp")
        new_token = new_service_token()
        second = app.credential(token_id="testapp-svc-2", sha256=hash_token(new_token))
        verifier = ServiceTokenVerifier(build_registry([app.registration((app.credential(), second))]).apps.values())
        self.assertEqual(verifier.verify([f"Bearer {app.token}"]).token_id, "testapp-svc-1")
        self.assertEqual(verifier.verify([f"Bearer {new_token}"]).token_id, "testapp-svc-2")

    def test_no_apps_means_nothing_authenticates(self) -> None:
        verifier = ServiceTokenVerifier([])
        with self.assertRaises(McpSecurityError):
            verifier.verify([f"Bearer {new_service_token()}"])


class LiveServiceAuthTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = make_world()
        cls.server = LiveServer(registry=cls.world.registry, adapters=cls.world.adapter_list).__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def assert_unauthenticated(self, response: httpx2.Response) -> dict:
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], 'Bearer realm="shared-mcp-server"')
        body = response.json()
        self.assertEqual(body["error"]["code"], -32001)
        self.assertEqual(body["error"]["message"], "Unauthenticated")
        self.assertEqual(body["error"]["data"]["error"], "UNAUTHENTICATED")
        self.assertTrue(body["error"]["data"]["correlation_id"].startswith("srv-"))
        self.assertNotIn("result", body)
        return body

    async def test_every_mcp_method_requires_service_token(self) -> None:
        t = self.world.testapp
        for body in (
            INITIALIZE,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc("tools/list"),
            rpc("tools/call", {"name": "testapp_echo_context", "arguments": {}}),
            rpc("ping"),
        ):
            with self.subTest(method=body["method"]):
                response = await post(self.server.mcp_url, body, base_headers(**{"X-MCP-User-Assertion": t.assertion()}))
                self.assert_unauthenticated(response)
        self.assertEqual(self.world.adapters["testapp"].calls, [])

    async def test_get_delete_and_unknown_paths_require_service_token(self) -> None:
        async with httpx2.AsyncClient(timeout=5) as http:
            for method, path in (("GET", "/mcp"), ("DELETE", "/mcp"), ("POST", "/mcp/"), ("GET", "/other"), ("POST", "/MCP")):
                with self.subTest(method=method, path=path):
                    response = await http.request(method, self.server.base_url + path, headers=base_headers())
                    self.assert_unauthenticated(response)

    async def test_invalid_tokens_get_identical_bodies(self) -> None:
        t = self.world.testapp
        bodies = []
        for value in (
            None,
            "Bearer garbage",
            f"Bearer {new_service_token()}",
            f"Bearer {t.token.replace('mcpsvc_', 'MCPSVC_')}",
            f"Basic {t.token}",
        ):
            headers = base_headers() if value is None else base_headers(Authorization=value)
            response = await post(self.server.mcp_url, INITIALIZE, headers)
            body = self.assert_unauthenticated(response)
            body["error"]["data"].pop("correlation_id")
            bodies.append(body)
            self.assertNotIn(t.token, response.text)
            self.assertNotIn("garbage", response.text)
        self.assertTrue(all(body == bodies[0] for body in bodies))

    async def test_duplicate_authorization_headers_rejected(self) -> None:
        t = self.world.testapp
        headers = list(base_headers().items()) + [("Authorization", f"Bearer {t.token}")] * 2
        async with httpx2.AsyncClient(timeout=5) as http:
            response = await http.post(self.server.mcp_url, json=INITIALIZE, headers=headers)
        self.assert_unauthenticated(response)

    async def test_valid_token_initializes_without_user_assertion(self) -> None:
        response = await post(self.server.mcp_url, INITIALIZE, self.world.testapp.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["protocolVersion"], PINNED)
        response = await post(self.server.mcp_url, rpc("ping", request_id=2), self.world.otherapp.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], {})

    async def test_health_endpoints_need_no_token(self) -> None:
        async with httpx2.AsyncClient(timeout=5) as http:
            for path in ("/healthz", "/readyz"):
                response = await http.get(self.server.base_url + path)
                self.assertEqual(response.status_code, 200, path)

    async def test_denials_are_audited_without_token_text(self) -> None:
        t = self.world.testapp
        with self.assertLogs("shared_mcp_server.audit", level="INFO") as logs:
            await post(self.server.mcp_url, INITIALIZE, base_headers())
            await post(self.server.mcp_url, INITIALIZE, base_headers(Authorization=f"Bearer {new_service_token()}"))
        records = [json.loads(r.getMessage()) for r in logs.records]
        denials = [r for r in records if r["event"] == "mcp.auth.service" and r["decision"] == "DENIED"]
        self.assertEqual([r["reason"] for r in denials], ["MISSING_TOKEN", "INVALID_TOKEN"])
        for line in logs.output:
            self.assertNotIn("mcpsvc_", line.replace("[REDACTED]", ""))
            self.assertNotIn(t.token, line)


class LiveExpiredTokenTests(unittest.TestCase):
    def test_expired_and_not_yet_valid_tokens_rejected(self) -> None:
        for label, credential_kwargs, reason in (
            ("expired", {"not_after": utc(timedelta(seconds=-5))}, "EXPIRED_TOKEN"),
            ("future", {"not_before": utc(timedelta(hours=1)), "not_after": utc(timedelta(days=1))}, "TOKEN_NOT_YET_VALID"),
        ):
            with self.subTest(label=label):
                app = AppCreds("testapp")
                world_registry = build_registry([app.registration((app.credential(**credential_kwargs),))])
                with LiveServer(registry=world_registry) as server:
                    with self.assertLogs("shared_mcp_server.audit", level="INFO") as logs:
                        response = httpx2.post(server.mcp_url, json=INITIALIZE, headers=app.headers(), timeout=5)
                self.assertEqual(response.status_code, 401)
                self.assertIn(reason, "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
