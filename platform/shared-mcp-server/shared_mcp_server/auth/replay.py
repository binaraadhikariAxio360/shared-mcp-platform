"""Single-use enforcement for user assertions.

DEVELOPMENT LIMITATION: the cache lives in process memory, so replay protection holds only for a
single server process (uvicorn `workers=1`, one replica). Running several workers or replicas
without a shared replay store (for example Redis `SET key NX EX`) would let an assertion be
replayed once per process. A shared store is required before any multi-worker deployment.
"""

from __future__ import annotations

import heapq
import threading
import time
from collections.abc import Callable

from ..errors import McpSecurityError


class ReplayCache:
    def __init__(self, max_entries: int = 50_000, clock: Callable[[], float] = time.time) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._clock = clock
        self._entries: dict[tuple[str, str], float] = {}
        self._expiry_heap: list[tuple[float, tuple[str, str]]] = []
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            self._purge(self._clock())
            return len(self._entries)

    def consume(self, issuer: str, jti: str, expires_at: float) -> bool:
        """Record `(issuer, jti)` until `expires_at`. Returns False if it was already used.

        Raises `McpSecurityError(MCP_UNAVAILABLE)` when the cache is full of unexpired entries:
        it fails closed and never evicts a live entry, since eviction would re-open replay.
        """
        key = (issuer, jti)
        with self._lock:
            now = self._clock()
            self._purge(now)
            if key in self._entries:
                return False
            if len(self._entries) >= self.max_entries:
                raise McpSecurityError("MCP_UNAVAILABLE", "REPLAY_CACHE_FULL")
            self._entries[key] = expires_at
            heapq.heappush(self._expiry_heap, (expires_at, key))
            return True

    def _purge(self, now: float) -> None:
        while self._expiry_heap and self._expiry_heap[0][0] <= now:
            expires_at, key = heapq.heappop(self._expiry_heap)
            if self._entries.get(key) == expires_at:
                del self._entries[key]
