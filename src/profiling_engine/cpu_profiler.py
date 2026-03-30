"""
cpu_profiler — cProfile-based CPU profiling with bottleneck detection.
"""

from __future__ import annotations

import cProfile
import os
import pstats
import subprocess
import sys
import json
import time
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any


@dataclass
class FunctionProfile:
    name: str
    filename: str
    lineno: int
    total_calls: int
    total_time: float  # seconds
    cumulative_time: float
    per_call_time: float
    is_bottleneck: bool = False


@dataclass
class ProfilingReport:
    target_file: str
    functions: list[FunctionProfile] = field(default_factory=list)
    total_time: float = 0.0
    bottleneck_threshold: float = 0.1  # 10% of total time
    max_recursion_depth: int = 0
    error: str | None = None

    @property
    def bottlenecks(self) -> list[FunctionProfile]:
        return [f for f in self.functions if f.is_bottleneck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_file": self.target_file,
            "total_time": round(self.total_time, 4),
            "total_functions_profiled": len(self.functions),
            "bottleneck_count": len(self.bottlenecks),
            "max_recursion_depth": self.max_recursion_depth,
            "error": self.error,
            "functions": [
                {
                    "name": f.name,
                    "file": f.filename,
                    "line": f.lineno,
                    "calls": f.total_calls,
                    "total_time": round(f.total_time, 6),
                    "cumulative_time": round(f.cumulative_time, 6),
                    "per_call": round(f.per_call_time, 6),
                    "is_bottleneck": f.is_bottleneck,
                }
                for f in self.functions[:50]
            ],
            "heatmap": [
                {"name": f.name, "time_pct": round(f.cumulative_time / max(self.total_time, 0.001) * 100, 1)}
                for f in self.functions[:20]
                if f.cumulative_time > 0
            ],
        }


class CPUProfiler:
    """Profile Python files using cProfile in a subprocess."""

    EXEC_TIMEOUT = 30

    def profile_file(self, target_file: str | Path, timeout: int | None = None) -> ProfilingReport:
        target = Path(target_file).resolve()
        report = ProfilingReport(target_file=str(target))
        timeout = timeout or self.EXEC_TIMEOUT

        wrapper_script = f'''
import cProfile
import pstats
import json
import sys
from io import StringIO

TARGET = {repr(str(target))}

profile = cProfile.Profile()
profile.enable()
try:
    with open(TARGET, "r", encoding="utf-8") as f:
        code = compile(f.read(), TARGET, "exec")
    exec(code, {{"__name__": "__main__", "__file__": TARGET}})
except SystemExit:
    pass
except Exception:
    pass
finally:
    profile.disable()

stats = pstats.Stats(profile, stream=StringIO())
stats.sort_stats("cumulative")

results = []
for key, value in stats.stats.items():
    filename, lineno, func_name = key
    cc, nc, tt, ct, callers = value
    results.append({{
        "name": func_name,
        "file": filename,
        "line": lineno,
        "calls": nc,
        "tottime": tt,
        "cumtime": ct,
    }})

print("PROFILE_JSON:" + json.dumps(results[:100], default=str))
'''

        try:
            result = subprocess.run(
                [sys.executable, "-c", wrapper_script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(target.parent),
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            for line in result.stdout.splitlines():
                if line.startswith("PROFILE_JSON:"):
                    data = json.loads(line[len("PROFILE_JSON:"):])
                    self._populate_report(report, data)
                    break

            if result.returncode != 0 and result.stderr:
                stderr_lines = result.stderr.strip().splitlines()
                report.error = stderr_lines[-1] if stderr_lines else None

        except subprocess.TimeoutExpired:
            report.error = f"Profiling timed out after {timeout}s"
        except Exception as exc:
            report.error = str(exc)

        return report

    def _populate_report(self, report: ProfilingReport, data: list[dict]) -> None:
        total_time = sum(d.get("tottime", 0) for d in data)
        report.total_time = total_time
        threshold = total_time * report.bottleneck_threshold

        for entry in data:
            calls = entry.get("calls", 0)
            tottime = entry.get("tottime", 0)
            cumtime = entry.get("cumtime", 0)
            per_call = cumtime / max(calls, 1)

            fp = FunctionProfile(
                name=entry.get("name", ""),
                filename=entry.get("file", ""),
                lineno=entry.get("line", 0),
                total_calls=calls,
                total_time=tottime,
                cumulative_time=cumtime,
                per_call_time=per_call,
                is_bottleneck=cumtime > threshold,
            )
            report.functions.append(fp)

        report.functions.sort(key=lambda f: f.cumulative_time, reverse=True)
