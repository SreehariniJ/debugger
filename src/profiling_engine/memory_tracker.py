"""
memory_tracker — tracemalloc-based memory allocation tracking.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MemoryAllocation:
    filename: str
    lineno: int
    size_bytes: int
    count: int


@dataclass
class MemoryReport:
    target_file: str
    peak_memory_bytes: int = 0
    current_memory_bytes: int = 0
    top_allocations: list[MemoryAllocation] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_file": self.target_file,
            "peak_memory_kb": round(self.peak_memory_bytes / 1024, 2),
            "current_memory_kb": round(self.current_memory_bytes / 1024, 2),
            "error": self.error,
            "top_allocations": [
                {
                    "file": a.filename,
                    "line": a.lineno,
                    "size_kb": round(a.size_bytes / 1024, 2),
                    "count": a.count,
                }
                for a in self.top_allocations[:20]
            ],
        }


class MemoryTracker:
    """Profile memory allocations using tracemalloc."""

    EXEC_TIMEOUT = 30

    def profile_file(self, target_file: str | Path, timeout: int | None = None) -> MemoryReport:
        target = Path(target_file).resolve()
        report = MemoryReport(target_file=str(target))
        timeout = timeout or self.EXEC_TIMEOUT

        wrapper_script = f'''
import tracemalloc
import json
import sys

TARGET = {repr(str(target))}

tracemalloc.start()
try:
    with open(TARGET, "r", encoding="utf-8") as f:
        code = compile(f.read(), TARGET, "exec")
    exec(code, {{"__name__": "__main__", "__file__": TARGET}})
except SystemExit:
    pass
except Exception:
    pass

snapshot = tracemalloc.take_snapshot()
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

stats = snapshot.statistics("lineno")
allocations = []
for stat in stats[:50]:
    frame = stat.traceback[0] if stat.traceback else None
    if frame:
        allocations.append({{
            "file": frame.filename,
            "line": frame.lineno,
            "size": stat.size,
            "count": stat.count,
        }})

result = {{"current": current, "peak": peak, "allocations": allocations}}
print("MEMORY_JSON:" + json.dumps(result, default=str))
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
                if line.startswith("MEMORY_JSON:"):
                    data = json.loads(line[len("MEMORY_JSON:"):])
                    report.current_memory_bytes = data.get("current", 0)
                    report.peak_memory_bytes = data.get("peak", 0)
                    for alloc in data.get("allocations", []):
                        report.top_allocations.append(MemoryAllocation(
                            filename=alloc.get("file", ""),
                            lineno=alloc.get("line", 0),
                            size_bytes=alloc.get("size", 0),
                            count=alloc.get("count", 0),
                        ))
                    break

        except subprocess.TimeoutExpired:
            report.error = f"Memory profiling timed out after {timeout}s"
        except Exception as exc:
            report.error = str(exc)

        return report
