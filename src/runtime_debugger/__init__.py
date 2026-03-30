"""
runtime_debugger — Controlled program execution with tracing and breakpoints.

Uses ``sys.settrace`` for line-level tracing and integrates with the
agent system to allow programmatic breakpoint setting, variable
inspection, and watchpoint evaluation.
"""

from runtime_debugger.trace_engine import TraceEngine, TraceEvent, ExecutionTrace
from runtime_debugger.breakpoint_manager import BreakpointManager, Breakpoint
from runtime_debugger.frame_inspector import FrameInspector
from runtime_debugger.watchpoint_tracker import WatchpointTracker

__all__ = [
    "TraceEngine",
    "TraceEvent",
    "ExecutionTrace",
    "BreakpointManager",
    "Breakpoint",
    "FrameInspector",
    "WatchpointTracker",
]
