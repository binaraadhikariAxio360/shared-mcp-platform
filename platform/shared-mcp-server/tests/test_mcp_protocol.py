"""MCP handshake, tools/list, protocol pinning, health and readiness over real Streamable HTTP."""

from __future__ import annotations

import unittest
from importlib.metadata import version

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from _live_server import LiveServer
from shared_mcp_server import SERVER_NAME, __version__

PINNED = "2025-11-25"
ACCEPT = "application/json, text/event-stream"


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


class LiveServerTestCase(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = LiveServer().__enter__()
        cls.mcp_url = cls.server.base_url + "/mcp"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    async def post(self, body: object, headers: dict | None = None) -> httpx2.Response:
        async with httpx2.AsyncClient(timeout=5) as http:
            return await http.post(
                self.mcp_url, json=body, headers={"Accept": ACCEPT, "Content-Type": "application/json", **(headers or {})}
            )


class SdkClientHandshakeTests(LiveServerTestCase):
    def test_installed_sdk_version(self) -> None:
        self.assertEqual(version("mcp"), "2.3.0")

    async def test_official_client_initialize_and_list_tools(self) -> None:
        async with httpx2.AsyncClient(timeout=5) as http:
            async with Client(streamable_http_client(self.mcp_url, http_client=http), mode="legacy") as client:
                self.assertEqual(client.protocol_version, PINNED)
                self.assertEqual(client.server_info.name, SERVER_NAME)
                self.assertEqual(client.server_info.version, __version__)
                result = await client.list_tools()
                self.assertEqual(result.tools, [])


class WireLevelTests(LiveServerTestCase):
    async def test_initialize_returns_pinned_version_and_server_info(self) -> None:
        response = await self.post(initialize_body())
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("mcp-session-id"))  # stateless
        body = response.json()
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["result"]["protocolVersion"], PINNED)
        self.assertEqual(body["result"]["serverInfo"]["name"], SERVER_NAME)

    async def test_tools_list_is_empty(self) -> None:
        response = await self.post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, {"MCP-Protocol-Version": PINNED}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"]["tools"], [])

    async def test_tools_call_unknown_tool_is_not_executed(self) -> None:
        response = await self.post(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "practicare_list_tasks", "arguments": {}}},
            {"MCP-Protocol-Version": PINNED},
        )
        body = response.json()
        self.assertTrue("error" in body or body["result"].get("isError") is True, body)

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
        # DNS-rebinding protection from the SDK stays active behind the guard.
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
                "registered_apps": 0,
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
