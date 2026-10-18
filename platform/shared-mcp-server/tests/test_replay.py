"""Single-use assertions (design §6 rows 15-18). In-memory cache: single-worker development only."""

from __future__ import annotations

import asyncio
import threading
import unittest

from _live_server import LiveServer
from _security_fixtures import call_body, make_world, post, rpc
from shared_mcp_server.auth.replay import ReplayCache
from shared_mcp_server.errors import McpSecurityError

TOOL = "testapp_echo_context"


class ReplayCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000.0
        self.cache = ReplayCache(max_entries=3, clock=lambda: self.now)

    def test_single_use(self) -> None:
        self.assertTrue(self.cache.consume("testapp", "jti-1", 1_060))
        self.assertFalse(self.cache.consume("testapp", "jti-1", 1_060))
        self.assertTrue(self.cache.consume("otherapp", "jti-1", 1_060))  # scoped per issuer

    def test_expired_entries_are_purged(self) -> None:
        self.cache.consume("testapp", "jti-1", 1_010)
        self.cache.consume("testapp", "jti-2", 1_100)
        self.now = 1_010
        self.assertEqual(len(self.cache), 1)
        # after its expiry the assertion itself is rejected by the exp check, so reuse of the slot is safe
        self.assertTrue(self.cache.consume("testapp", "jti-1", 1_070))

    def test_full_cache_fails_closed_without_evicting(self) -> None:
        for jti in ("a", "b", "c"):
            self.assertTrue(self.cache.consume("testapp", jti, 1_060))
        with self.assertRaises(McpSecurityError) as caught:
            self.cache.consume("testapp", "d", 1_060)
        self.assertEqual((caught.exception.code, caught.exception.reason), ("MCP_UNAVAILABLE", "REPLAY_CACHE_FULL"))
        self.assertFalse(self.cache.consume("testapp", "a", 1_060))  # live entries were kept
        self.now = 1_060
        self.assertTrue(self.cache.consume("testapp", "d", 1_120))  # room again after expiry

    def test_concurrent_threads_same_jti_exactly_one_wins(self) -> None:
        cache = ReplayCache()
        results: list[bool] = []
        barrier = threading.Barrier(20)

        def worker() -> None:
            barrier.wait()
            results.append(cache.consume("testapp", "jti-shared", 9e12))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results.count(True), 1)

    def test_invalid_size(self) -> None:
        with self.assertRaises(ValueError):
            ReplayCache(max_entries=0)


class LiveReplayTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = make_world()
        cls.server = LiveServer(registry=cls.world.registry, adapters=cls.world.adapter_list).__enter__()
        cls.cache = cls.server.app.state.server_state.assertions.replay_cache

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.__exit__(None, None, None)

    def setUp(self) -> None:
        self.world.adapters["testapp"].calls.clear()

    async def call(self, assertion: str) -> dict:
        response = await post(self.server.mcp_url, call_body(TOOL, {"limit": 1}), self.world.testapp.headers(assertion))
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_same_assertion_twice_sequentially(self) -> None:
        t = self.world.testapp
        assertion = t.assertion("tools/call", TOOL)
        first = await self.call(assertion)
        self.assertIn("result", first)
        second = await self.call(assertion)
        self.assertEqual(second["error"]["data"]["error"], "UNAUTHENTICATED")
        self.assertEqual(len(self.world.adapters["testapp"].calls), 1)

        listing = t.assertion()
        ok = await post(self.server.mcp_url, rpc("tools/list"), t.headers(listing))
        replay = await post(self.server.mcp_url, rpc("tools/list"), t.headers(listing))
        self.assertIn("result", ok.json())
        self.assertEqual(replay.json()["error"]["data"]["error"], "UNAUTHENTICATED")

    async def test_same_assertion_in_twenty_concurrent_calls(self) -> None:
        assertion = self.world.testapp.assertion("tools/call", TOOL)
        results = await asyncio.gather(*(self.call(assertion) for _ in range(20)))
        self.assertEqual(sum("result" in r for r in results), 1)
        self.assertEqual(sum(r.get("error", {}).get("data", {}).get("error") == "UNAUTHENTICATED" for r in results), 19)
        self.assertEqual(len(self.world.adapters["testapp"].calls), 1)

    async def test_twenty_concurrent_calls_with_distinct_assertions(self) -> None:
        t = self.world.testapp
        results = await asyncio.gather(*(self.call(t.assertion("tools/call", TOOL)) for _ in range(20)))
        self.assertTrue(all("result" in r and not r["result"]["isError"] for r in results))
        self.assertEqual(len(self.world.adapters["testapp"].calls), 20)

    async def test_full_cache_fails_closed(self) -> None:
        original = self.cache.max_entries
        self.cache.max_entries = len(self.cache)
        try:
            body = await self.call(self.world.testapp.assertion("tools/call", TOOL))
        finally:
            self.cache.max_entries = original
        self.assertEqual(body["error"]["code"], -32603)
        self.assertEqual(body["error"]["data"]["error"], "MCP_UNAVAILABLE")
        self.assertEqual(self.world.adapters["testapp"].calls, [])


if __name__ == "__main__":
    unittest.main()
