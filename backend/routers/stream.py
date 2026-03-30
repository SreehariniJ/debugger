"""
stream.py — SSE streaming router for real-time debug pipeline updates.

Works with both in-memory EventBus and Redis Pub/Sub EventBus.
The get_event_bus() factory auto-detects which is available.

Endpoints:
    GET  /stream/{task_id}     → SSE event stream
    GET  /task/{task_id}       → Polling fallback (task status)
    GET  /task/{task_id}/result → Fetch completed result
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.services.event_bus import get_event_bus, get_event_bus_mode

router = APIRouter(tags=["streaming"])


@router.get("/stream/{task_id}")
async def stream_task(task_id: str):
    """
    Server-Sent Events endpoint for real-time pipeline updates.

    Works identically whether backed by in-memory or Redis Pub/Sub.
    """
    bus = get_event_bus()
    mode = get_event_bus_mode()

    # Verify the task exists
    if mode == "redis":
        status = await bus.async_get_task_status(task_id) if hasattr(bus, 'async_get_task_status') else bus.get_task_status(task_id)
    else:
        status = bus.get_task_status(task_id)

    if status["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found. It may have expired or never existed.",
        )

    return StreamingResponse(
        bus.subscribe(task_id, timeout_seconds=120),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Polling fallback — returns current task status."""
    bus = get_event_bus()
    mode = get_event_bus_mode()

    if mode == "redis" and hasattr(bus, 'async_get_task_status'):
        return await bus.async_get_task_status(task_id)
    return bus.get_task_status(task_id)


@router.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """Retrieve the final result payload of a completed task."""
    bus = get_event_bus()
    mode = get_event_bus_mode()

    if mode == "redis" and hasattr(bus, 'async_get_result'):
        result = await bus.async_get_result(task_id)
    else:
        result = bus.get_result(task_id)

    if result is None:
        if mode == "redis" and hasattr(bus, 'async_get_task_status'):
            status = await bus.async_get_task_status(task_id)
        else:
            status = bus.get_task_status(task_id)

        if status["status"] == "not_found":
            raise HTTPException(status_code=404, detail="Task not found.")
        raise HTTPException(status_code=202, detail="Task still running.")
    return result
