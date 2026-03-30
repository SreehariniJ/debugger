"""
watchpoint_tracker — Monitors variable conditions during execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime_debugger.trace_engine import TraceEvent


@dataclass
class WatchConfig:
    variable: str
    condition: str  # Python expression, e.g. "x < 0" or "len(items) > 100"
    description: str = ""


@dataclass
class WatchpointTrigger:
    watchpoint: WatchConfig
    event_index: int
    lineno: int
    filename: str
    variable_value: str
    local_vars: dict[str, str]


class WatchpointTracker:
    """Evaluates watchpoint conditions against trace events."""

    def __init__(self) -> None:
        self._watchpoints: list[WatchConfig] = []

    def add(self, variable: str, condition: str, description: str = "") -> None:
        self._watchpoints.append(WatchConfig(
            variable=variable,
            condition=condition,
            description=description,
        ))

    def remove(self, variable: str) -> bool:
        before = len(self._watchpoints)
        self._watchpoints = [w for w in self._watchpoints if w.variable != variable]
        return len(self._watchpoints) < before

    def clear(self) -> None:
        self._watchpoints.clear()

    def evaluate(self, events: list[TraceEvent]) -> list[WatchpointTrigger]:
        """Evaluate all watchpoints against a list of trace events."""
        triggers: list[WatchpointTrigger] = []

        for i, event in enumerate(events):
            if event.event_type != "line":
                continue

            for wp in self._watchpoints:
                if wp.variable not in event.local_vars:
                    continue

                try:
                    ctx = {k: self._coerce(v) for k, v in event.local_vars.items()}
                    if eval(wp.condition, {"__builtins__": {}}, ctx):
                        triggers.append(WatchpointTrigger(
                            watchpoint=wp,
                            event_index=i,
                            lineno=event.lineno,
                            filename=event.filename,
                            variable_value=event.local_vars[wp.variable],
                            local_vars=event.local_vars,
                        ))
                except Exception:
                    continue

        return triggers

    @staticmethod
    def _coerce(repr_str: str) -> Any:
        """Try to coerce a repr string back to a value for condition evaluation."""
        try:
            return eval(repr_str, {"__builtins__": {}}, {})
        except Exception:
            return repr_str
