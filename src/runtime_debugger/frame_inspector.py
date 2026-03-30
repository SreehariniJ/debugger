"""
frame_inspector — Extracts and serializes stack frame information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime_debugger.trace_engine import TraceEvent, ExecutionTrace


@dataclass
class FrameSnapshot:
    function_name: str
    filename: str
    lineno: int
    local_vars: dict[str, str]
    depth: int


@dataclass
class StackSnapshot:
    frames: list[FrameSnapshot] = field(default_factory=list)
    error_context: str | None = None

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "function": f.function_name,
                "file": f.filename,
                "line": f.lineno,
                "vars": f.local_vars,
                "depth": f.depth,
            }
            for f in self.frames
        ]


class FrameInspector:
    """Extracts stack snapshots from execution traces."""

    def snapshot_at_event(self, trace: ExecutionTrace, event_index: int) -> StackSnapshot:
        """Reconstruct the call stack at a specific trace event."""
        if event_index >= len(trace.events):
            return StackSnapshot()

        target_event = trace.events[event_index]
        stack: list[FrameSnapshot] = []

        # Walk backwards through events to reconstruct the call stack
        call_stack: list[TraceEvent] = []
        for i in range(event_index + 1):
            ev = trace.events[i]
            if ev.event_type == "call":
                call_stack.append(ev)
            elif ev.event_type == "return" and call_stack:
                call_stack.pop()

        # Convert call stack to frame snapshots
        for ev in call_stack:
            stack.append(FrameSnapshot(
                function_name=ev.function_name,
                filename=ev.filename,
                lineno=ev.lineno,
                local_vars=ev.local_vars,
                depth=ev.depth,
            ))

        # Add the current event
        stack.append(FrameSnapshot(
            function_name=target_event.function_name,
            filename=target_event.filename,
            lineno=target_event.lineno,
            local_vars=target_event.local_vars,
            depth=target_event.depth,
        ))

        snapshot = StackSnapshot(frames=stack)
        if target_event.exception_info:
            snapshot.error_context = target_event.exception_info

        return snapshot

    def snapshot_at_error(self, trace: ExecutionTrace) -> StackSnapshot | None:
        """Get the stack snapshot at the first exception event."""
        for i, ev in enumerate(trace.events):
            if ev.event_type == "exception":
                return self.snapshot_at_event(trace, i)
        return None

    def variable_history(self, trace: ExecutionTrace, var_name: str) -> list[dict[str, Any]]:
        """Track the value of a specific variable across the entire trace."""
        history: list[dict[str, Any]] = []
        for i, ev in enumerate(trace.events):
            if ev.event_type == "line" and var_name in ev.local_vars:
                history.append({
                    "event_index": i,
                    "lineno": ev.lineno,
                    "filename": ev.filename,
                    "function": ev.function_name,
                    "value": ev.local_vars[var_name],
                })
        return history
