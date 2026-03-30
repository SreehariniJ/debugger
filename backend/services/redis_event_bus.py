"""
redis_event_bus.py — Redis Pub/Sub implementation of the EventBus interface.

This is the distributed replacement for the in-memory EventBus.
It uses Redis Pub/Sub so that:
  - Celery workers (separate processes) can publish events
  - FastAPI (web process) can subscribe and stream via SSE

Architecture:
    ┌─────────────────┐  PUBLISH task:{id}   ┌───────────┐
    │  Celery Worker   │ ──────────────────► │   Redis    │
    │  (tasks.py)      │                     │  Pub/Sub   │
    └─────────────────┘                      │           │
                                             │ Channel:  │
    ┌─────────────────┐  SUBSCRIBE task:{id} │ task:{id} │
    │  FastAPI SSE     │ ◄────────────────── │           │
    │  (stream.py)     │   async generator   └───────────┘
    └─────────────────┘

Each task_id maps to a Redis channel: "task:{task_id}"
Events are JSON-serialized and published as messages.
Task status/results are also stored in Redis keys for polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Any, Optional

logger = logging.getLogger("offline_debugger.redis_event_bus")

# Re-use the same EventType and StreamEvent from the in-memory bus
from backend.services.event_bus import EventType, StreamEvent


def _channel_name(task_id: str) -> str:
    """Redis channel name for a task."""
    return f"task:{task_id}"


def _status_key(task_id: str) -> str:
    """Redis key for task status."""
    return f"task_status:{task_id}"


def _result_key(task_id: str) -> str:
    """Redis key for task result."""
    return f"task_result:{task_id}"


class RedisEventBus:
    """
    Redis Pub/Sub event bus — drop-in replacement for the in-memory EventBus.

    - publish() uses a sync Redis client (safe from Celery workers)
    - subscribe() uses an async Redis client (for FastAPI SSE endpoints)
    - Task status and results are persisted in Redis keys (TTL = 10 min)
    """

    def __init__(self, redis_url: str, key_ttl_seconds: int = 600):
        self._redis_url = redis_url
        self._key_ttl = key_ttl_seconds
        self._sync_client = None
        self._async_client = None

    def _get_sync_client(self):
        """Lazy-init sync Redis client (for Celery workers)."""
        if self._sync_client is None:
            import redis
            self._sync_client = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
        return self._sync_client

    async def _get_async_client(self):
        """Lazy-init async Redis client (for FastAPI)."""
        if self._async_client is None:
            import redis.asyncio as aioredis
            self._async_client = aioredis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
        return self._async_client

    # ── Publish (sync — called from Celery workers) ─────────────────────

    def publish(self, task_id: str, event_type: EventType, data: dict[str, Any]) -> None:
        """
        Publish an event to the Redis channel for this task.

        This is intentionally SYNCHRONOUS so it can be called from
        Celery worker tasks (which run in a separate process).
        """
        r = self._get_sync_client()
        channel = _channel_name(task_id)

        evt = StreamEvent(event=event_type, data=data)
        message = json.dumps({
            "event": event_type.value,
            "data": data,
            "timestamp": evt.timestamp,
        })

        # Publish to channel
        r.publish(channel, message)

        # Update task status in Redis
        status = "completed" if event_type in (EventType.COMPLETE, EventType.ERROR) else "running"
        r.hset(_status_key(task_id), mapping={
            "status": status,
            "last_event": event_type.value,
            "last_message": data.get("message", ""),
            "updated_at": str(time.time()),
        })
        r.expire(_status_key(task_id), self._key_ttl)

        # Store result if this is a result event
        if event_type == EventType.RESULT:
            r.set(_result_key(task_id), json.dumps(data), ex=self._key_ttl)

        logger.debug("Redis published %s to %s: %s", event_type.value, channel, data.get("message", ""))

    # ── Subscribe (async — called from FastAPI SSE endpoint) ────────────

    async def subscribe(
        self,
        task_id: str,
        timeout_seconds: float = 120,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that subscribes to a Redis channel and yields
        SSE-formatted strings as events arrive.
        """
        client = await self._get_async_client()
        pubsub = client.pubsub()
        channel = _channel_name(task_id)

        await pubsub.subscribe(channel)
        deadline = time.time() + timeout_seconds

        try:
            while time.time() < deadline:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0),
                    timeout=3.0,
                )

                if message and message["type"] == "message":
                    raw = message["data"]
                    try:
                        parsed = json.loads(raw)
                        event_type = parsed.get("event", "stage")
                        # Format as SSE
                        sse_line = f"event: {event_type}\ndata: {raw}\n\n"
                        yield sse_line

                        # Terminal events
                        if event_type in ("complete", "error"):
                            return
                    except json.JSONDecodeError:
                        logger.warning("Malformed Redis message on %s: %s", channel, raw)
                        continue
                else:
                    # No message — send keepalive
                    yield ": keepalive\n\n"

                    # Check if task already completed (late subscriber)
                    status = await self._async_get_status(task_id)
                    if status.get("status") == "completed":
                        return

            # Timeout
            timeout_evt = StreamEvent(
                event=EventType.ERROR,
                data={"message": "Stream timed out.", "code": "TIMEOUT"},
            )
            yield timeout_evt.to_sse()

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    # ── Status / Result (async — for FastAPI polling endpoints) ─────────

    async def _async_get_status(self, task_id: str) -> dict[str, Any]:
        client = await self._get_async_client()
        data = await client.hgetall(_status_key(task_id))
        if not data:
            return {"status": "not_found", "task_id": task_id}
        return {
            "status": data.get("status", "unknown"),
            "task_id": task_id,
            "last_event": data.get("last_event"),
            "last_message": data.get("last_message"),
        }

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Sync status check (also works from non-async contexts)."""
        r = self._get_sync_client()
        data = r.hgetall(_status_key(task_id))
        if not data:
            return {"status": "not_found", "task_id": task_id}
        return {
            "status": data.get("status", "unknown"),
            "task_id": task_id,
            "last_event": data.get("last_event"),
            "last_message": data.get("last_message"),
        }

    def get_result(self, task_id: str) -> Optional[dict[str, Any]]:
        """Retrieve the final result payload."""
        r = self._get_sync_client()
        raw = r.get(_result_key(task_id))
        if raw:
            return json.loads(raw)
        return None

    async def async_get_task_status(self, task_id: str) -> dict[str, Any]:
        return await self._async_get_status(task_id)

    async def async_get_result(self, task_id: str) -> Optional[dict[str, Any]]:
        client = await self._get_async_client()
        raw = await client.get(_result_key(task_id))
        if raw:
            return json.loads(raw)
        return None


# ── Singleton ───────────────────────────────────────────────────────────────
_redis_bus: Optional[RedisEventBus] = None


def get_redis_event_bus() -> RedisEventBus:
    """Return the global RedisEventBus singleton."""
    global _redis_bus
    if _redis_bus is None:
        from backend.config import REDIS_URL
        _redis_bus = RedisEventBus(redis_url=REDIS_URL)
    return _redis_bus
