from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class TimedLRUCache:
    """Unified timed LRU cache with hit/miss tracking and lazy expiry sweep."""

    __slots__ = (
        "ttl_seconds", "max_entries", "_lock", "_items",
        "_hits", "_misses", "_access_count", "_SWEEP_INTERVAL",
    )

    def __init__(self, ttl_seconds: int, max_entries: int):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._access_count = 0
        self._SWEEP_INTERVAL = 100

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            self._access_count += 1

            item = self._items.get(key)
            if not item:
                self._misses += 1
                return None

            expires_at, value = item
            if expires_at < now:
                self._items.pop(key, None)
                self._misses += 1
                return None

            self._items.move_to_end(key, last=True)
            self._hits += 1

            # Lazy expiry sweep every N accesses
            if self._access_count % self._SWEEP_INTERVAL == 0:
                self._sweep_expired(now)

            return value

    def set(self, key: str, value: Any) -> None:
        expires_at = time.monotonic() + self.ttl_seconds
        with self._lock:
            self._items[key] = (expires_at, value)
            self._items.move_to_end(key, last=True)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _sweep_expired(self, now: float) -> None:
        """Remove expired entries. Called under lock."""
        expired_keys = [k for k, (exp, _) in self._items.items() if exp < now]
        for k in expired_keys:
            self._items.pop(k, None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._items),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            }


# Backward-compatible aliases
TimedResponseCache = TimedLRUCache
TimedValueCache = TimedLRUCache


class InMemoryRateLimiter:
    """Simple fixed-window in-memory rate limiter by client host."""

    def __init__(self, limit_per_minute: int):
        self.limit_per_minute = limit_per_minute
        self._lock = threading.Lock()
        self._counter: dict[tuple[str, int], int] = {}
        self._current_window = int(time.time() // 60)

    def allow(self, client_id: str) -> bool:
        now_window = int(time.time() // 60)
        with self._lock:
            if now_window != self._current_window:
                self._counter.clear()
                self._current_window = now_window

            key = (client_id, now_window)
            current = self._counter.get(key, 0)
            if current >= self.limit_per_minute:
                return False
            self._counter[key] = current + 1
            return True

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "limit_per_minute": self.limit_per_minute,
                "window": self._current_window,
                "tracked_buckets": len(self._counter),
            }
