"""
trace_engine — Line-level execution tracing via ``sys.settrace``.

Records every line execution, function call/return, and exception as
structured ``TraceEvent`` objects.  Produces an ``ExecutionTrace`` that
feeds into the dynamic analysis and root cause engines.
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
import json
import traceback
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TraceEvent:
    event_type: str  # "line", "call", "return", "exception"
    filename: str
    lineno: int
    function_name: str
    local_vars: dict[str, str] = field(default_factory=dict)  # name → repr
    return_value: str | None = None
    exception_info: str | None = None
    timestamp: float = 0.0
    depth: int = 0  # call stack depth


@dataclass
class ExecutionTrace:
    target_file: str
    events: list[TraceEvent] = field(default_factory=list)
    error_message: str | None = None
    exit_code: int | None = None
    execution_time: float = 0.0
    max_depth: int = 0
    total_lines_executed: int = 0
    line_hit_counts: dict[str, dict[int, int]] = field(default_factory=dict)

    def lines_for_file(self, filepath: str) -> dict[int, int]:
        return self.line_hit_counts.get(filepath, {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_file": self.target_file,
            "total_events": len(self.events),
            "error_message": self.error_message,
            "exit_code": self.exit_code,
            "execution_time": round(self.execution_time, 4),
            "max_depth": self.max_depth,
            "total_lines_executed": self.total_lines_executed,
            "events": [
                {
                    "type": e.event_type,
                    "file": e.filename,
                    "line": e.lineno,
                    "function": e.function_name,
                    "vars": e.local_vars,
                    "return": e.return_value,
                    "exception": e.exception_info,
                    "depth": e.depth,
                }
                for e in self.events[:2000]  # Cap serialized events
            ],
        }


class TraceEngine:
    """
    Executes a Python file with ``sys.settrace`` instrumentation.

    Captures line-by-line execution, variable snapshots, call/return events,
    and exceptions.  Designed to run the target in a subprocess with a
    tracing wrapper script to isolate the debugger from the target.
    """

    MAX_EVENTS = 50_000
    MAX_VAR_REPR_LEN = 200
    EXEC_TIMEOUT = 15  # seconds

    def __init__(self, workspace_root: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None

    def trace_file(self, target_file: str | Path, timeout: int | None = None) -> ExecutionTrace:
        """Execute target file with tracing and return the execution trace."""
        target = Path(target_file).resolve()
        timeout = timeout or self.EXEC_TIMEOUT

        trace = ExecutionTrace(target_file=str(target))
        start = time.monotonic()

        # Build the tracing wrapper script
        wrapper_script = self._build_wrapper_script(str(target))

        try:
            result = subprocess.run(
                [sys.executable, "-c", wrapper_script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(target.parent),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            trace.exit_code = result.returncode

            # Parse trace data from stdout (JSON lines)
            self._parse_trace_output(result.stdout, trace, str(target))

            if result.returncode != 0 and result.stderr:
                stderr_lines = result.stderr.strip().splitlines()
                trace.error_message = stderr_lines[-1] if stderr_lines else "Unknown error"

        except subprocess.TimeoutExpired:
            trace.error_message = f"Execution timed out after {timeout}s"
            trace.exit_code = -1
        except Exception as exc:
            trace.error_message = f"Trace engine error: {exc}"
            trace.exit_code = -2

        trace.execution_time = time.monotonic() - start
        return trace

    def _build_wrapper_script(self, target_path: str) -> str:
        """Build a Python script that traces execution of the target and outputs JSON."""
        return f'''
import sys
import json
import os

_EVENTS = []
_DEPTH = [0]
_MAX_EVENTS = {self.MAX_EVENTS}
_TARGET = {repr(target_path)}
_LINE_HITS = {{}}

def _safe_repr(val, maxlen={self.MAX_VAR_REPR_LEN}):
    try:
        r = repr(val)
        return r[:maxlen] if len(r) > maxlen else r
    except Exception:
        return "<repr-error>"

def _tracer(frame, event, arg):
    if len(_EVENTS) >= _MAX_EVENTS:
        return None

    fname = frame.f_code.co_filename
    # Only trace files in the workspace, not stdlib
    if not fname.startswith(os.path.dirname(_TARGET)):
        return _tracer

    lineno = frame.f_lineno
    func_name = frame.f_code.co_name

    entry = {{"t": event, "f": fname, "l": lineno, "fn": func_name, "d": _DEPTH[0]}}

    if event == "call":
        _DEPTH[0] += 1
    elif event == "return":
        entry["rv"] = _safe_repr(arg)
        _DEPTH[0] = max(0, _DEPTH[0] - 1)
    elif event == "exception":
        exc_type, exc_value, _ = arg
        entry["ex"] = f"{{exc_type.__name__}}: {{exc_value}}"
    elif event == "line":
        # Capture local variables (limited to 10 for performance)
        local_vars = {{}}
        for k, v in list(frame.f_locals.items())[:10]:
            if not k.startswith("_"):
                local_vars[k] = _safe_repr(v)
        entry["v"] = local_vars

        # Track line hit counts
        key = fname
        _LINE_HITS.setdefault(key, {{}})
        _LINE_HITS[key][lineno] = _LINE_HITS[key].get(lineno, 0) + 1

    _EVENTS.append(entry)
    return _tracer

sys.settrace(_tracer)
try:
    with open(_TARGET, "r", encoding="utf-8") as f:
        code = compile(f.read(), _TARGET, "exec")
    exec(code, {{"__name__": "__main__", "__file__": _TARGET}})
except SystemExit:
    pass
except Exception:
    import traceback
    traceback.print_exc()
finally:
    sys.settrace(None)

# Output trace as JSON
output = {{"events": _EVENTS, "hits": _LINE_HITS}}
print("TRACE_JSON:" + json.dumps(output, default=str))
'''

    def _parse_trace_output(self, stdout: str, trace: ExecutionTrace, target_file: str) -> None:
        """Parse the JSON trace output from the subprocess."""
        for line in stdout.splitlines():
            if line.startswith("TRACE_JSON:"):
                try:
                    data = json.loads(line[len("TRACE_JSON:"):])
                    events = data.get("events", [])
                    for e in events:
                        trace.events.append(TraceEvent(
                            event_type=e.get("t", ""),
                            filename=e.get("f", ""),
                            lineno=e.get("l", 0),
                            function_name=e.get("fn", ""),
                            local_vars=e.get("v", {}),
                            return_value=e.get("rv"),
                            exception_info=e.get("ex"),
                            depth=e.get("d", 0),
                        ))
                    trace.line_hit_counts = data.get("hits", {})
                    trace.total_lines_executed = sum(
                        sum(counts.values())
                        for counts in trace.line_hit_counts.values()
                    )
                    trace.max_depth = max(
                        (e.depth for e in trace.events), default=0
                    )
                except (json.JSONDecodeError, KeyError):
                    pass
                break
