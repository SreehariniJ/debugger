from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class TimedResponseCache:
    def __init__(self, ttl_seconds: int, max_entries: int):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._items: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None

            expires_at, value = item
            if expires_at < now:
                self._items.pop(key, None)
                return None

            self._items.move_to_end(key, last=True)
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

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._items),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


class TimedValueCache:
    def __init__(self, ttl_seconds: int, max_entries: int):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._items: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None

            expires_at, value = item
            if expires_at < now:
                self._items.pop(key, None)
                return None

            self._items.move_to_end(key, last=True)
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

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._items),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }


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

