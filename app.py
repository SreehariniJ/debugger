import os
import sys
import subprocess
import traceback
import asyncio
import difflib
import tempfile
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import time

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from scanner import CodeScanner
from rag_engine import LocalRAGEngine
from agents import DebuggingAgents

app = FastAPI(title="Offline Debugger API v4.0 — Ultra Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scanner = CodeScanner(".")
rag = LocalRAGEngine(data_dir="knowledge_base")
agents = DebuggingAgents()
executor = ThreadPoolExecutor(max_workers=6)


class DebugRequest(BaseModel):
    file_path: str

class SnippetRequest(BaseModel):
    code: str

class DiffRequest(BaseModel):
    original: str
    fixed: str

class ComplexityRequest(BaseModel):
    code: str

class ApplyFixRequest(BaseModel):
    file_path: str
    fixed_code: str

class DebugResponse(BaseModel):
    error: Optional[str] = None
    analysis: Optional[str] = None
    explanation: Optional[str] = None
    verification: Optional[str] = None
    fixed_code: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[int] = None
    complexity: Optional[Dict[str, Any]] = None
    security_audit: Optional[Dict[str, Any]] = None
    topology: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, float]] = None
    total_time: Optional[float] = None
    success: bool


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "model_loaded": agents.llm is not None,
        "model_path": agents.model_path,
        "engine": "Elite Secure Pipeline v5.5.0 (Sub-ms Latency)"
    }

def run_target_code(file_path):
    try:
        result = subprocess.run(
            [sys.executable, file_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return None
        error_lines = result.stderr.strip().splitlines()
        return error_lines[-1] if error_lines else "Unknown execution error"
    except subprocess.TimeoutExpired:
        return "TimeoutError: The script execution took too long (potential infinite loop)."
    except Exception as e:
        return str(e)

async def run_in_executor(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func, *args)


# Simple local cache for LLM responses
debug_cache = {}

async def _run_debug_pipeline(file_path: str) -> DebugResponse:
    grand_start = time.time()

    error_msg = await run_in_executor(run_target_code, file_path)
    if not error_msg:
        code_text = ""
        complexity_data = None
        security_data = None
        try:
            with open(file_path) as f:
                code_text = f.read()
            complexity_data = agents.complexity_agent(code_text)
            security_data = agents.security_audit_agent(code_text)
        except Exception:
            pass # Keep complexity and security_audit as None if file read or analysis fails
        return DebugResponse(
            success=True,
            error=None,
            complexity=complexity_data,
            security_audit=security_data,
            total_time=round(time.time() - grand_start, 2)
        )

    try:
        try:
            with open(file_path) as f:
                code_text = f.read()
        except Exception:
            code_text = ""

        # Cache check (Key = code + error)
        cache_key = f"{code_text}_{error_msg}"
        if cache_key in debug_cache:
            cached = debug_cache[cache_key]
            # Create a copy with updated time
            new_cached = cached.model_copy()
            new_cached.total_time = round(time.time() - grand_start, 2)
            new_cached.metrics = {"cache_status": 1.0} # Float for type safety
            return new_cached

        # ─── Phase 1: Static + Parallel Scan ───
        p1 = time.time()
        code_context, local_knowledge, severity, complexity, security_data = await asyncio.gather(
            run_in_executor(scanner.get_context_for_file, file_path),
            run_in_executor(rag.query_docs, error_msg),
            run_in_executor(agents.severity_agent, error_msg),
            run_in_executor(agents.complexity_agent, code_text),
            run_in_executor(agents.security_audit_agent, code_text),
        )
        p1_time = round(time.time() - p1, 2)

        # ─── Phase 2: Viper Orchestration (Orchestrated Multi-Agent Loop) ───
        p2 = time.time()
        workspace_files = scanner.scan_workspace()
        orchestration_result = await agents.viper_orchestration(error_msg, code_context, workspace_files)
        p2_time = round(float(time.time() - p2), 2)

        # ─── Phase 3: Final Analysis & Confidence ───
        p3 = time.time()
        fixed_code = orchestration_result.get("fix", "")
        analysis_data = await run_in_executor(agents.multi_agent_pipeline, error_msg, code_context, local_knowledge)
        p3_time = round(float(time.time() - p3), 2)

        confidence = agents.confidence_agent(error_msg, str(analysis_data.get("analysis", "")), str(fixed_code))
        total_time = round(float(time.time() - grand_start), 2)

        response = DebugResponse(
            success=False,
            error=error_msg,
            analysis=analysis_data.get("analysis"),
            explanation=analysis_data.get("explanation"),
            verification=orchestration_result.get("path_taken"),
            fixed_code=fixed_code,
            severity=severity,
            confidence=confidence,
            complexity=complexity,
            security_audit=security_data,
            metrics={
                "scan_rag": float(p1_time),
                "viper_orchestration": float(p2_time),
                "final_synthesis": float(p3_time)
            },
            total_time=total_time
        )
        
        # Save to cache
        debug_cache[cache_key] = response
        return response

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/debug", response_model=DebugResponse)
async def debug_file(request: DebugRequest):
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return await _run_debug_pipeline(request.file_path)


@app.post("/debug_snippet", response_model=DebugResponse)
async def debug_snippet(request: SnippetRequest):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=".", prefix="_snippet_"
    ) as tmp:
        tmp.write(request.code)
        tmp_path = tmp.name
    try:
        return await _run_debug_pipeline(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.post("/analyze_complexity")
async def analyze_complexity(request: ComplexityRequest):
    """Instant AST-based code complexity analysis — no LLM."""
    result = agents.complexity_agent(request.code)
    return result


@app.get("/scan_project")
async def scan_project():
    """Elite feature: Full workspace scan."""
    files = scanner.scan_workspace()
    return {"files": files, "count": len(files)}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file for debugging."""
    try:
        uploads_dir = "uploads"
        if not os.path.exists(uploads_dir):
            os.makedirs(uploads_dir)
        
        file_path = os.path.join(uploads_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
        
        # Trigger debug pipeline on the uploaded file
        return await _run_debug_pipeline(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/diff")
async def compute_diff(request: DiffRequest):
    orig_lines = request.original.splitlines(keepends=True)
    fixed_lines = request.fixed.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, fixed_lines,
        fromfile="original.py", tofile="fixed.py", lineterm=""
    ))
    return {"diff": "".join(diff)}


@app.post("/apply_fix")
async def apply_fix(request: ApplyFixRequest):
    try:
        clean_code = request.fixed_code.replace("```python", "").replace("```", "").strip()
        fixed_filename = f"fixed_{os.path.basename(request.file_path)}"
        target_dir = os.path.dirname(request.file_path) or "."
        full_path = os.path.join(target_dir, fixed_filename)
        with open(full_path, "w") as f:
            f.write(clean_code)
        return {"message": f"Fixed file created at {full_path}", "path": full_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Serve Frontend ---
frontend_path = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")

    @app.get("/{rest_of_path:path}")
    async def serve_frontend(rest_of_path: str):
        # API routes are handled before this catch-all
        return FileResponse(os.path.join(frontend_path, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
