"""MCP handshake, tools/list, protocol pinning, health and readiness over real Streamable HTTP.

Step 2 guarantees, re-checked with Step 3 authentication in front (design §6 row 30), plus the
official SDK client flows that the Step 6 PractiCare client will rely on.
"""

from __future__ import annotations

import json
import typing
import unittest
from importlib.metadata import version

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from _live_server import LiveServer
from _security_fixtures import ACCEPT, PINNED, AppCreds, make_world
from shared_mcp_server import SERVER_NAME, __version__


def initialize_body(protocol_version: str = PINNED, request_id: int = 1) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "step2-test", "version": "0"},
        },
    }


class PerRequestAssertionAuth(httpx2.Auth):
    """What the Step 6 client must do: a fresh assertion for every tools/list and tools/call POST.

    The SDK client re-sends the same headers for initialize, notifications and every request on a
    connection, and `call_tool` issues a hidden `tools/list` to fetch output schemas; a single
    per-connection assertion is therefore not enough (design conflict C11).
    """

    requires_request_body = True

    def __init__(self, creds: AppCreds, **claims: typing.Any) -> None:
        self.creds = creds
        self.claims = claims
        self.minted: list[str] = []

    def auth_flow(self, request: httpx2.Request) -> typing.Generator[httpx2.Request, httpx2.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.creds.token}"
        try:
            message = json.loads(request.content or b"null")
        except ValueError:
            message = None
        method = message.get("method") if isinstance(message, dict) else None
        if method in ("tools/list", "tools/call"):
            tool = message["params"]["name"] if method == "tools/call" else None
            request.headers["X-MCP-User-Assertion"] = self.creds.assertion(method, tool, **self.claims)
            self.minted.append(method)
        yield request


class LiveServerTestCase(unittest.IsolatedAsyncioTestCase):
    with_tools = False

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = make_world(with_tools=cls.with_tools)
        cls.creds = cls.world.testapp
        cls.server = LiveServer(registry=cls.world.registry, adapters=cls.world.adapter_list).__enter__()
        cls.mcp_url = cls.server.mcp_url

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    async def post(self, body: object, headers: dict | None = None, *, authenticated: bool = True) -> httpx2.Response:
        base = {"Accept": ACCEPT, "Content-Type": "application/json"}
        if authenticated:
            base["Authorization"] = f"Bearer {self.creds.token}"
        async with httpx2.AsyncClient(timeout=5) as http:
            return await http.post(self.mcp_url, json=body, headers={**base, **(headers or {})})


class SdkClientHandshakeTests(LiveServerTestCase):
    def test_installed_sdk_version(self) -> None:
        self.assertEqual(version("mcp"), "2.3.0")

    async def test_official_client_initialize_and_list_tools(self) -> None:
        # One assertion in the connection headers: initialize and notifications/initialized do not
        # consume it; tools/list does.
        headers = {"Authorization": f"Bearer {self.creds.token}", "X-MCP-User-Assertion": self.creds.assertion()}
        async with httpx2.AsyncClient(timeout=5, headers=headers) as http:
            async with Client(streamable_http_client(self.mcp_url, http_client=http), mode="legacy") as client:
                self.assertEqual(client.protocol_version, PINNED)
                self.assertEqual(client.server_info.name, SERVER_NAME)
                self.assertEqual(client.server_info.version, __version__)
                result = await client.list_tools()
                self.assertEqual(result.tools, [])
                with self.assertRaises(MCPError) as caught:  # same assertion again: single use
                    await client.list_tools()
                self.assertEqual(caught.exception.code, -32001)

    async def test_official_client_without_service_token_fails_loudly(self) -> None:
        async with httpx2.AsyncClient(timeout=5) as http:
            with self.assertRaises(BaseException):
                async with Client(streamable_http_client(self.mcp_url, http_client=http), mode="legacy"):
                    pass


class SdkClientToolCallTests(LiveServerTestCase):
    with_tools = True

    async def test_per_request_assertions_support_call_tool(self) -> None:
        auth = PerRequestAssertionAuth(self.creds, role="NURSE_STAFF", tid="tenant-001")
        async with httpx2.AsyncClient(timeout=5, auth=auth) as http:
            async with Client(streamable_http_client(self.mcp_url, http_client=http), mode="legacy") as client:
                result = await client.call_tool("testapp_echo_context", {"limit": 2})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["tenant_id"], "tenant-001")
        # call_tool triggered a hidden tools/list (output-schema refresh); each got its own assertion
        self.assertEqual(auth.minted, ["tools/call", "tools/list"])

    async def test_single_connection_assertion_cannot_cover_call_tool(self) -> None:
        # Documents C11: the hidden tools/list re-sends the tools/call assertion and is refused.
        # The failure is explicit (an exception), never a silent empty success.
        headers = {
            "Authorization": f"Bearer {self.creds.token}",
            "X-MCP-User-Assertion": self.creds.assertion("tools/call", "testapp_echo_context"),
        }
        async with httpx2.AsyncClient(timeout=5, headers=headers) as http:
            async with Client(streamable_http_client(self.mcp_url, http_client=http), mode="legacy") as client:
                with self.assertRaises(MCPError) as caught:
                    await client.call_tool("testapp_echo_context", {"limit": 1})
        self.assertEqual(caught.exception.code, -32001)


class WireLevelTests(LiveServerTestCase):
    async def test_initialize_returns_pinned_version_and_server_info(self) -> None:
        response = await self.post(initialize_body())
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("mcp-session-id"))  # stateless
        body = response.json()
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["result"]["protocolVersion"], PINNED)
        self.assertEqual(body["result"]["serverInfo"]["name"], SERVER_NAME)

    async def test_tools_list_is_empty_for_an_app_without_tools(self) -> None:
        response = await self.post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"MCP-Protocol-Version": PINNED, "X-MCP-User-Assertion": self.creds.assertion(role="CLINIC_OWNER")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["tools"], [])

    async def test_tools_call_unknown_tool_is_not_executed(self) -> None:
        response = await self.post(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "practicare_list_tasks", "arguments": {}}},
            {
                "MCP-Protocol-Version": PINNED,
                "X-MCP-User-Assertion": self.creds.assertion("tools/call", "practicare_list_tasks"),
            },
        )
        body = response.json()
        self.assertEqual(body["error"]["data"]["error"], "NOT_FOUND")

    async def test_unauthenticated_requests_rejected_before_protocol_checks(self) -> None:
        for body, headers in (
            (initialize_body(), {}),
            (initialize_body("2024-11-05"), {}),
            ({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}, {"MCP-Protocol-Version": PINNED}),
        ):
            response = await self.post(body, headers, authenticated=False)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("result", response.json())

    async def test_initialize_with_other_handshake_versions_rejected(self) -> None:
        for requested in ("2024-11-05", "2025-03-26", "2025-06-18", "2026-07-28", "9999-01-01"):
            with self.subTest(requested=requested):
                response = await self.post(initialize_body(requested, request_id=7))
                self.assertEqual(response.status_code, 400)
                error = response.json()
                self.assertEqual(error["id"], 7)
                self.assertEqual(error["error"]["data"], {"supported": [PINNED], "requested": requested})

    async def test_initialize_with_conflicting_header_rejected(self) -> None:
        response = await self.post(initialize_body(), {"MCP-Protocol-Version": "2025-06-18"})
        self.assertEqual(response.status_code, 400)

    async def test_requests_without_or_with_wrong_version_header_rejected(self) -> None:
        request = {"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}}
        for headers in ({}, {"MCP-Protocol-Version": "2025-06-18"}, {"MCP-Protocol-Version": "2026-07-28"}):
            with self.subTest(headers=headers):
                response = await self.post(request, headers)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["data"]["supported"], [PINNED])

    async def test_modern_server_discover_rejected(self) -> None:
        response = await self.post(
            {"jsonrpc": "2.0", "id": 5, "method": "server/discover", "params": {}}, {"MCP-Protocol-Version": "2026-07-28"}
        )
        self.assertEqual(response.status_code, 400)

    async def test_oversized_body_rejected(self) -> None:
        response = await self.post({"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {"x": "a" * 300_000}})
        self.assertEqual(response.status_code, 413)

    async def test_foreign_host_header_rejected(self) -> None:
        # DNS-rebinding protection from the SDK stays active behind the guards.
        response = await self.post(initialize_body(), {"Host": "evil.example.com"})
        self.assertIn(response.status_code, (400, 403, 421))
        self.assertNotIn("result", response.text)


class HealthAndReadinessTests(LiveServerTestCase):
    async def test_healthz(self) -> None:
        async with httpx2.AsyncClient(timeout=5) as http:
            response = await http.get(self.server.base_url + "/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "server": SERVER_NAME, "version": __version__})

    async def test_readyz_when_running(self) -> None:
        async with httpx2.AsyncClient(timeout=5) as http:
            response = await http.get(self.server.base_url + "/readyz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ready",
                "protocol_version": PINNED,
                "transport": "streamable-http",
                "registered_apps": 2,
                "registered_tools": 0,
            },
        )

    def test_readyz_not_ready_before_startup_and_after_shutdown(self) -> None:
        live = LiveServer()
        state = live.app.state.server_state
        self.assertFalse(state.ready)
        with live:
            self.assertTrue(state.ready)
            response = httpx2.get(live.base_url + "/readyz", timeout=5)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["registered_apps"], 0)  # production default: no apps
        self.assertFalse(state.ready)

    async def test_readyz_returns_503_when_not_ready(self) -> None:
        state = self.server.app.state.server_state
        state.ready = False
        try:
            async with httpx2.AsyncClient(timeout=5) as http:
                response = await http.get(self.server.base_url + "/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "not_ready"})
        finally:
            state.ready = True


if __name__ == "__main__":
    unittest.main()
