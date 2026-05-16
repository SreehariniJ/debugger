"""
event_bus.py — In-memory async event bus for SSE streaming.

Architecture:
    ┌──────────────────┐      publish()      ┌──────────────────┐
    │  Background Task │ ──────────────────►  │    EventBus      │
    │  (debug pipeline)│                      │                  │
    └──────────────────┘                      │  task_id → deque │
                                              │  task_id → Event │
    ┌──────────────────┐     subscribe()      │                  │
    │  SSE endpoint    │ ◄────────────────── │                  │
    │  /stream/{id}    │   (async generator)  └──────────────────┘
    └──────────────────┘

Each task_id gets an independent event channel. The SSE endpoint
yields events as they arrive. When the task completes or errors,
a terminal event is sent and the channel is cleaned up.

This is the "simple local version" — no Redis dependency. For
horizontal scaling, swap to Redis Pub/Sub with the same interface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Any, Optional

from backend.config import EVENTBUS_TTL_SECONDS, EVENTBUS_MAX_EVENTS

logger = logging.getLogger("offline_debugger.event_bus")


class EventType(str, Enum):
    """Event types for the SSE stream."""
    STAGE = "stage"           # Pipeline stage transition
    PROGRESS = "progress"     # Progress update within a stage
    PARTIAL = "partial"       # Partial result (e.g., streaming tokens)
    RESULT = "result"         # Final result payload
    ERROR = "error"           # Error occurred
    COMPLETE = "complete"     # Task completed (terminal)


@dataclass
class StreamEvent:
    """A single event in the SSE stream."""
    event: EventType
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_sse(self) -> str:
        """Format as an SSE-compliant string."""
        payload = {
            "event": self.event.value,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"event: {self.event.value}\ndata: {json.dumps(payload)}\n\n"


class EventBus:
    """
    Thread-safe, async-aware in-memory event bus.

    - publish() can be called from sync or async code.
    - subscribe() is an async generator for SSE endpoints.
    - Channels auto-expire after a configurable TTL.
    """

    def __init__(self, channel_ttl_seconds: int = EVENTBUS_TTL_SECONDS, max_events_per_channel: int = EVENTBUS_MAX_EVENTS):
        self._channels: dict[str, deque[StreamEvent]] = defaultdict(
            lambda: deque(maxlen=max_events_per_channel)
        )
        self._waiters: dict[str, asyncio.Event] = {}
        self._completed: set[str] = set()
        self._created_at: dict[str, float] = {}
        self._ttl = channel_ttl_seconds
        self._lock = asyncio.Lock()

    def publish(self, task_id: str, event_type: EventType, data: dict[str, Any]) -> None:
        """
        Publish an event to a task channel.

        Safe to call from both sync and async contexts.
        """
        evt = StreamEvent(event=event_type, data=data)
        self._channels[task_id].append(evt)

        if task_id not in self._created_at:
            self._created_at[task_id] = time.time()

        if event_type in (EventType.COMPLETE, EventType.ERROR, EventType.RESULT):
            self._completed.add(task_id)

        if task_id not in self._waiters:
            self._waiters[task_id] = asyncio.Event()
        self._waiters[task_id].set()

        logger.debug("Published %s to task %s: %s", event_type.value, task_id, data.get("message", ""))

    async def subscribe(
        self,
        task_id: str,
        timeout_seconds: float = 120,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted strings for a task.

        Blocks until new events arrive or the task completes.
        Automatically closes after the terminal event or timeout.
        """
        cursor = 0
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            channel = self._channels.get(task_id)

            if channel and cursor < len(channel):
                # Yield all events from cursor to end
                events = list(channel)[cursor:]
                cursor += len(events)
                for evt in events:
                    yield evt.to_sse()

                    # If this was a terminal event, we're done
                    if evt.event in (EventType.COMPLETE, EventType.ERROR):
                        return
            else:
                if task_id not in self._waiters:
                    self._waiters[task_id] = asyncio.Event()
                waiter = self._waiters[task_id]
                waiter.clear()
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    # Send a keepalive comment to prevent connection timeout
                    yield ": keepalive\n\n"

                    # Check if task was completed while we waited
                    if task_id in self._completed and cursor >= len(self._channels.get(task_id, [])):
                        return

        # Timeout reached
        yield StreamEvent(
            event=EventType.ERROR,
            data={"message": "Stream timed out.", "code": "TIMEOUT"},
        ).to_sse()

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Get the current status of a task (for polling fallback)."""
        channel = self._channels.get(task_id)
        if not channel:
            return {"status": "not_found", "task_id": task_id}

        last_event = channel[-1] if channel else None
        is_done = task_id in self._completed

        return {
            "status": "completed" if is_done else "running",
            "task_id": task_id,
            "event_count": len(channel),
            "last_event": last_event.event.value if last_event else None,
            "last_message": last_event.data.get("message") if last_event else None,
        }

    def get_result(self, task_id: str) -> Optional[dict[str, Any]]:
        """Retrieve the final result payload if the task completed."""
        channel = self._channels.get(task_id)
        if not channel:
            return None
        for evt in reversed(channel):
            if evt.event == EventType.RESULT:
                return evt.data
        return None

    async def cleanup_expired(self) -> int:
        """Remove channels older than TTL. Returns count removed."""
        now = time.time()
        expired = [
            tid for tid, created in self._created_at.items()
            if now - created > self._ttl
        ]
        for tid in expired:
            self._channels.pop(tid, None)
            self._waiters.pop(tid, None)
            self._completed.discard(tid)
            self._created_at.pop(tid, None)
        if expired:
            logger.info("Cleaned up %d expired task channels.", len(expired))
        return len(expired)


# ── Unified Factory ─────────────────────────────────────────────────────────
# Auto-detects whether to use Redis Pub/Sub or in-memory EventBus.
# All consumers call get_event_bus() and get the correct implementation.

_bus = None
_bus_mode: str | None = None


def get_event_bus():
    """
    Return the appropriate EventBus singleton.

    - If USE_DISTRIBUTED=true and Redis is reachable → RedisEventBus
    - Otherwise → in-memory EventBus (default, zero-dependency)

    The returned object implements the same interface:
        .publish(task_id, event_type, data)
        .subscribe(task_id, timeout_seconds) → AsyncGenerator
        .get_task_status(task_id) → dict
        .get_result(task_id) → dict | None
    """
    global _bus, _bus_mode

    if _bus is not None:
        return _bus

    from backend.config import USE_DISTRIBUTED

    if USE_DISTRIBUTED:
        try:
            from backend.services.redis_event_bus import get_redis_event_bus
            redis_bus = get_redis_event_bus()
            # Test connectivity
            redis_bus._get_sync_client().ping()
            _bus = redis_bus
            _bus_mode = "redis"
            logger.info("EventBus: using Redis Pub/Sub (distributed mode)")
            return _bus
        except Exception as exc:
            logger.warning(
                "Redis not available (%s), falling back to in-memory EventBus.", exc
            )

    _bus = EventBus()
    _bus_mode = "memory"
    logger.info("EventBus: using in-memory mode (single-process)")
    return _bus


def get_event_bus_mode() -> str:
    """Return 'redis' or 'memory' indicating which bus is active."""
    if _bus_mode is None:
        get_event_bus()  # Force initialization
    return _bus_mode or "memory"
