"""
runtime — FastAPI router for runtime debugging endpoints.

All user code execution is delegated to the Docker-based sandbox engine
(backend.services.sandbox). No subprocess.run() calls exist in this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from backend.services.sandbox import execute_file, execute_snippet, SandboxResult

# Add src to path for trace engine imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

router = APIRouter(tags=["runtime"])


# ── Request Models ──────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    file_path: str
    timeout: int = Field(default=10, ge=1, le=30)


class RunSnippetRequest(BaseModel):
    code: str
    timeout: int = Field(default=10, ge=1, le=30)


class TraceRequest(BaseModel):
    file_path: str
    timeout: int = Field(default=15, ge=1, le=60)


class BreakpointRequest(BaseModel):
    file_path: str
    line: int
    condition: Optional[str] = None


class WatchpointRequest(BaseModel):
    variable: str
    condition: str
    description: str = ""


class VariableHistoryRequest(BaseModel):
    file_path: str
    variable: str
    timeout: int = Field(default=15, ge=1, le=60)


# ── Sandbox-backed execution ───────────────────────────────────────────────

def _execute_python_safely(file_path: str, timeout: int = 10) -> dict:
    """
    Execute a Python file inside the secure Docker sandbox.

    This replaces the former subprocess.run() implementation that was
    vulnerable to Remote Code Execution (RCE).
    """
    result: SandboxResult = execute_file(file_path, timeout=timeout)
    return result.to_dict()


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_file(req: RunRequest):
    """Execute a Python file inside a sandboxed Docker container."""
    result = _execute_python_safely(req.file_path, timeout=req.timeout)
    return result


@router.post("/run_snippet")
async def run_snippet_route(req: RunSnippetRequest):
    """Execute a Python code snippet inside a sandboxed Docker container."""
    result: SandboxResult = execute_snippet(req.code, timeout=req.timeout)
    return result.to_dict()


@router.post("/trace")
async def trace_file(req: TraceRequest):
    """Execute a file with sys.settrace instrumentation."""
    try:
        from runtime_debugger import TraceEngine
        engine = TraceEngine()
        trace = engine.trace_file(req.file_path, timeout=req.timeout)
        return trace.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/trace/variable_history")
async def variable_history(req: VariableHistoryRequest):
    """Trace a file and return the history of a specific variable."""
    try:
        from runtime_debugger import TraceEngine
        from runtime_debugger.frame_inspector import FrameInspector
        engine = TraceEngine()
        trace = engine.trace_file(req.file_path, timeout=req.timeout)
        inspector = FrameInspector()
        history = inspector.variable_history(trace, req.variable)
        return {"variable": req.variable, "history": history, "total_events": len(trace.events)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
