"""
profiling — FastAPI router for CPU and memory profiling endpoints.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

router = APIRouter(tags=["profiling"])


class ProfileRequest(BaseModel):
    file_path: str
    timeout: int = Field(default=30, ge=1, le=120)


@router.post("/cpu")
async def cpu_profile(req: ProfileRequest):
    """Profile CPU usage of a target file."""
    try:
        from profiling_engine import CPUProfiler
        profiler = CPUProfiler()
        report = profiler.profile_file(req.file_path, timeout=req.timeout)
        return report.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/memory")
async def memory_profile(req: ProfileRequest):
    """Profile memory allocations of a target file."""
    try:
        from profiling_engine import MemoryTracker
        tracker = MemoryTracker()
        report = tracker.profile_file(req.file_path, timeout=req.timeout)
        return report.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
