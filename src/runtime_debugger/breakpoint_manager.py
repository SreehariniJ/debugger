"""
breakpoint_manager — Manages breakpoints and conditional breakpoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Breakpoint:
    file: str
    line: int
    condition: str | None = None
    hit_count: int = 0
    enabled: bool = True
    log_message: str | None = None  # tracepoint / logpoint

    @property
    def key(self) -> str:
        return f"{self.file}:{self.line}"


class BreakpointManager:
    """Manages a set of breakpoints for use by the trace engine."""

    def __init__(self) -> None:
        self._breakpoints: dict[str, Breakpoint] = {}

    def add(self, file: str, line: int, condition: str | None = None) -> Breakpoint:
        bp = Breakpoint(file=file, line=line, condition=condition)
        self._breakpoints[bp.key] = bp
        return bp

    def remove(self, file: str, line: int) -> bool:
        key = f"{file}:{line}"
        return self._breakpoints.pop(key, None) is not None

    def toggle(self, file: str, line: int) -> bool:
        key = f"{file}:{line}"
        bp = self._breakpoints.get(key)
        if bp:
            bp.enabled = not bp.enabled
            return bp.enabled
        return False

    def should_break(self, filename: str, lineno: int, local_vars: dict[str, Any] | None = None) -> bool:
        key = f"{filename}:{lineno}"
        bp = self._breakpoints.get(key)
        if not bp or not bp.enabled:
            return False

        bp.hit_count += 1

        if bp.condition:
            try:
                ctx = dict(local_vars or {})
                return bool(eval(bp.condition, {"__builtins__": {}}, ctx))
            except Exception:
                return False

        return True

    def get_all(self) -> list[Breakpoint]:
        return list(self._breakpoints.values())

    def clear(self) -> None:
        self._breakpoints.clear()

    def to_dict(self) -> list[dict[str, Any]]:
        return [
            {
                "file": bp.file,
                "line": bp.line,
                "condition": bp.condition,
                "hit_count": bp.hit_count,
                "enabled": bp.enabled,
            }
            for bp in self._breakpoints.values()
        ]
