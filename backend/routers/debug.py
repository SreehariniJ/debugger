import asyncio
import ast
import hashlib
import tempfile
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.config import (
    ENABLE_SECURITY_AUDIT,
    FAST_MODE_DEFAULT,
    MAX_SNIPPET_CHARS,
    MAX_UPLOAD_BYTES,
    PIPELINE_CONCURRENCY,
    UPLOAD_DIR,
    get_workspace_root,
    logger,
)
from backend.dependencies import (
    get_agents,
    get_analysis_cache,
    get_debug_cache,
    get_pipeline_semaphore,
    get_rag,
    get_scanner,
    run_in_executor,
)
from backend.schemas import (
    ApplyFixRequest,
    BatchDebugRequest,
    ComplexityRequest,
    DebugRequest,
    DebugResponse,
    DiffRequest,
    SnippetRequest,
    ValidateFixRequest,
)
from backend.services.event_bus import EventType, get_event_bus, get_event_bus_mode
from backend.services.sandbox import execute_file
from backend.utils import (
    _generate_unified_diff,
    _safe_resolve_workspace_path,
    _safe_upload_name,
)
from agents import ModelConfigurationError, ModelInferenceError

router = APIRouter(tags=["debug"])


def _cache_key(code: str, error: str) -> str:
    content = f"{code}!!{error}"
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def _syntax_check(code: str) -> tuple[bool, str | None]:
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as exc:
        return False, str(exc)


def _sanitize_markdown_code(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if len(lines) > 2:
            return "\n".join(lines[1:-1])
    return clean


def _ast_signature(code: str) -> str | None:
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None
    return ast.dump(parsed, annotate_fields=False, include_attributes=False)


def _fix_changes_behavior(original_code: str, fixed_code: str) -> bool:
    clean_original = original_code.strip()
    clean_fixed = fixed_code.strip()
    if not clean_fixed or clean_fixed == clean_original:
        return False

    original_signature = _ast_signature(clean_original)
    fixed_signature = _ast_signature(clean_fixed)
    if original_signature and fixed_signature:
        return original_signature != fixed_signature

    return True


def _verify_generated_fix(path: Path, fixed_code: str) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=path.suffix or ".py",
        delete=False,
        dir=str(UPLOAD_DIR),
        prefix="_verified_fix_",
        encoding="utf-8",
    ) as tmp:
        tmp.write(fixed_code)
        tmp_path = Path(tmp.name)

    try:
        execution = execute_file(str(tmp_path))
        error_msg = _execution_error_message(
            tmp_path,
            execution.stdout,
            execution.stderr,
            execution.exit_code,
            execution.timed_out,
        )
        return {
            "resolved": error_msg is None,
            "error": error_msg,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "exit_code": execution.exit_code,
            "timed_out": execution.timed_out,
            "error_type": execution.error_type,
            "backend": execution.backend,
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _build_model_failure_response(
    *,
    pipeline_mode: str,
    code_text: str,
    response_source_path: str | None,
    execution,
    complexity,
    security_data,
    severity: str,
    total_time: float,
    exc: Exception,
) -> DebugResponse:
    logger.exception("Debug pipeline model failure: %s", exc)
    return DebugResponse(
        success=False,
        error="Model inference failed",
        details=str(exc),
        analysis="The code execution failure was captured, but the AI model could not generate a valid fix.",
        explanation="Check the model configuration, prompt output, or local runtime and try again.",
        verification="Model inference failed before a verified patch could be produced.",
        fixed_code=None,
        severity=severity,
        confidence=1,
        complexity=complexity,
        security_audit=security_data,
        beginner_explanation="The runtime error was reproduced, but model inference failed.",
        learning_tips=[
            "Confirm the configured Qwen model file exists and loads successfully.",
            "Review the model failure details before retrying the debug run.",
        ],
        error_concept=execution.error_type or "ModelInferenceError",
        metrics={
            "scan_rag": 0.0,
            "viper_orchestration": 0.0,
            "final_synthesis": 0.0,
            "execution": float(execution.duration),
            "fast_mode": 1.0 if pipeline_mode == "fast" else 0.0,
            "cache_status": 0.0,
        },
        total_time=round(total_time, 3),
        source_path=response_source_path,
        source_code=code_text,
        pipeline_mode=pipeline_mode,
        stdout=execution.stdout,
        stderr=execution.stderr,
        exit_code=execution.exit_code,
        timed_out=execution.timed_out,
        error_line=execution.error_line,
        error_type=execution.error_type,
        execution_backend=execution.backend,
    )


async def _get_cached_code_analytics(
    code_text: str,
    agents,
    analysis_cache,
    include_security: bool = False,
):
    digest = hashlib.sha256(code_text.encode("utf-8", errors="ignore")).hexdigest()
    cache_key = f"analytics:{digest}:sec={include_security}"

    cached = analysis_cache.get(cache_key)
    if cached:
        return cached["complexity"], cached["security"]

    complexity = await run_in_executor(agents.complexity_agent, code_text)
    security = None
    if include_security:
        security = await run_in_executor(agents.security_audit_agent, code_text)

    analysis_cache.set(cache_key, {"complexity": complexity, "security": security})
    return complexity, security


def _execution_error_message(path: Path, stdout: str, stderr: str, exit_code: int, timed_out: bool) -> str | None:
    if timed_out:
        return stderr.strip() or f"Execution timed out while running {path.name}."
    if exit_code == 0:
        return None
    if stderr.strip():
        return stderr.strip()
    if stdout.strip():
        return stdout.strip()
    return f"Execution failed for {path.name} with exit code {exit_code}."


def _build_learning_tips(error_type: str | None, timed_out: bool) -> list[str]:
    if timed_out:
        return [
            "Add clear termination conditions around loops and retries.",
            "Use smaller test inputs while debugging long-running code.",
        ]

    tips_by_error = {
        "ZeroDivisionError": [
            "Validate denominators before division.",
            "Return a fallback value when the divisor can be zero.",
        ],
        "SyntaxError": [
            "Run a syntax check before execution to catch parser issues early.",
            "Review indentation and unmatched brackets around the failing line.",
        ],
        "NameError": [
            "Initialize variables before the first read.",
            "Check for typos between declaration and usage sites.",
        ],
        "TypeError": [
            "Inspect the runtime types flowing into the failing expression.",
            "Add guards or conversions before combining incompatible values.",
        ],
    }
    return tips_by_error.get(
        error_type or "",
        [
            "Reproduce the failure with the smallest possible input.",
            "Trace the state leading into the failing line before patching it.",
        ],
    )


def _normalise_confidence(value: int | None, default: int = 7) -> int:
    if value is None:
        return default
    return max(1, min(10, int(value)))


def _source_path_for_response(path: Path) -> str | None:
    return None if path.name.startswith("_snippet_") else str(path)


async def _run_debug_pipeline(
    path: Path,
    mode: str | None,
    agents,
    scanner,
    rag,
    debug_cache,
    analysis_cache,
) -> DebugResponse:
    grand_start = time.time()
    path_text = str(path)
    pipeline_mode = mode or ("fast" if FAST_MODE_DEFAULT else "full")
    fast_mode = pipeline_mode == "fast"

    try:
        code_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="File could not be read.") from exc

    execution = await run_in_executor(execute_file, path_text)
    error_msg = _execution_error_message(
        path,
        execution.stdout,
        execution.stderr,
        execution.exit_code,
        execution.timed_out,
    )
    execution_success = error_msg is None
    response_source_path = _source_path_for_response(path)

    if not execution_success:
        cache_signature = (
            f"{error_msg}|line={execution.error_line}|type={execution.error_type}|mode={pipeline_mode}"
        )
        cache_key = f"{_cache_key(code_text, cache_signature)}:mode={pipeline_mode}"
        cached = debug_cache.get(cache_key)
        if cached:
            result = cached.model_copy(deep=True)
            result.total_time = round(time.time() - grand_start, 3)
            result.stdout = execution.stdout
            result.stderr = execution.stderr
            result.exit_code = execution.exit_code
            result.timed_out = execution.timed_out
            result.error_line = execution.error_line
            result.error_type = execution.error_type
            result.execution_backend = execution.backend
            result.source_code = code_text
            result.source_path = response_source_path
            result.metrics = {**(result.metrics or {}), "cache_status": 1.0}
            return result
    else:
        cache_key = None

    include_security = (not fast_mode) and ENABLE_SECURITY_AUDIT

    analytics_task = _get_cached_code_analytics(
        code_text,
        agents,
        analysis_cache,
        include_security=include_security,
    )

    if execution_success:
        complexity, security_data = await analytics_task
        total_time = round(time.time() - grand_start, 3)
        return DebugResponse(
            success=True,
            error=None,
            analysis=None,
            explanation="Execution completed successfully.",
            verification=f"Runtime completed with exit code 0 via {execution.backend}.",
            fixed_code=None,
            severity="INFO",
            confidence=10,
            complexity=complexity,
            security_audit=security_data,
            beginner_explanation="The program ran without raising an exception.",
            learning_tips=[],
            error_concept=None,
            metrics={
                "scan_rag": 0.0,
                "viper_orchestration": 0.0,
                "final_synthesis": 0.0,
                "execution": float(execution.duration),
                "fast_mode": 1.0 if fast_mode else 0.0,
                "cache_status": 0.0,
            },
            total_time=total_time,
            source_path=response_source_path,
            source_code=code_text,
            pipeline_mode=pipeline_mode,
            stdout=execution.stdout,
            stderr=execution.stderr,
            exit_code=execution.exit_code,
            timed_out=execution.timed_out,
            error_line=execution.error_line,
            error_type=execution.error_type,
            execution_backend=execution.backend,
        )

    if fast_mode:
        p1_start = time.time()
        severity, analytics = await asyncio.gather(
            run_in_executor(agents.severity_agent, error_msg),
            analytics_task,
        )
        complexity, security_data = analytics
        p1_time = round(time.time() - p1_start, 3)

        p2_start = time.time()
        try:
            analysis_data, fixed_code = await asyncio.gather(
                run_in_executor(agents.multi_agent_pipeline, error_msg, code_text, ""),
                run_in_executor(agents.code_fixer_agent, code_text, error_msg, 1),
            )
        except (ModelConfigurationError, ModelInferenceError) as exc:
            return _build_model_failure_response(
                pipeline_mode=pipeline_mode,
                code_text=code_text,
                response_source_path=response_source_path,
                execution=execution,
                complexity=complexity,
                security_data=security_data,
                severity=severity,
                total_time=time.time() - grand_start,
                exc=exc,
            )
        p2_time = round(time.time() - p2_start, 3)
        fix_verification = await run_in_executor(_verify_generated_fix, path, fixed_code)
        confidence = _normalise_confidence(
            agents.confidence_agent(error_msg, str(analysis_data.get("analysis", "")), fixed_code),
            default=7,
        )
        confidence = min(10, confidence + 1) if fix_verification["resolved"] else max(1, confidence - 2)
        verification_text = (
            "Model-generated fix verified in sandbox."
            if fix_verification["resolved"]
            else f"Model-generated fix failed sandbox verification: {fix_verification['error']}"
        )

        response = DebugResponse(
            success=False,
            error=error_msg,
            details=None,
            analysis=analysis_data.get("analysis"),
            explanation=analysis_data.get("explanation"),
            verification=verification_text,
            fixed_code=fixed_code or None,
            severity=severity,
            confidence=confidence,
            complexity=complexity,
            security_audit=security_data,
            beginner_explanation=(
                f"The script crashed with {execution.error_type or 'a runtime error'} during execution."
            ),
            learning_tips=_build_learning_tips(execution.error_type, execution.timed_out),
            error_concept=execution.error_type or ("Timeout" if execution.timed_out else "RuntimeError"),
            metrics={
                "scan_rag": float(p1_time),
                "viper_orchestration": float(p2_time),
                "final_synthesis": 0.0,
                "execution": float(execution.duration),
                "fast_mode": 1.0,
                "cache_status": 0.0,
            },
            total_time=round(time.time() - grand_start, 3),
            source_path=response_source_path,
            source_code=code_text,
            pipeline_mode=pipeline_mode,
            stdout=execution.stdout,
            stderr=execution.stderr,
            exit_code=execution.exit_code,
            timed_out=execution.timed_out,
            error_line=execution.error_line,
            error_type=execution.error_type,
            execution_backend=execution.backend,
        )

        if cache_key:
            debug_cache.set(cache_key, response)
        return response

    p1_start = time.time()
    knowledge_query = error_msg[-2000:] if error_msg else path.name
    code_context, local_knowledge, severity, analytics = await asyncio.gather(
        run_in_executor(scanner.get_context_for_file, path_text),
        run_in_executor(rag.query_docs, knowledge_query),
        run_in_executor(agents.severity_agent, error_msg),
        analytics_task,
    )
    complexity, security_data = analytics
    p1_time = round(time.time() - p1_start, 3)

    p2_start = time.time()

    async def _phase2_fix():
        context_text = code_context or code_text
        workspace_files = await run_in_executor(scanner.scan_workspace)
        return await agents.viper_orchestration(error_msg, context_text, workspace_files)

    async def _phase3_synthesis():
        return await run_in_executor(
            agents.multi_agent_pipeline,
            error_msg,
            code_context or code_text,
            local_knowledge,
        )

    try:
        orchestration_result, analysis_data = await asyncio.gather(_phase2_fix(), _phase3_synthesis())
    except (ModelConfigurationError, ModelInferenceError) as exc:
        return _build_model_failure_response(
            pipeline_mode=pipeline_mode,
            code_text=code_text,
            response_source_path=response_source_path,
            execution=execution,
            complexity=complexity,
            security_data=security_data,
            severity=severity,
            total_time=time.time() - grand_start,
            exc=exc,
        )
    p2_time = round(time.time() - p2_start, 3)

    fixed_code = orchestration_result.get("fix") or None
    analysis_text = analysis_data.get("analysis")
    explanation_text = analysis_data.get("explanation")
    fix_verification = await run_in_executor(_verify_generated_fix, path, fixed_code) if fixed_code else None
    confidence = _normalise_confidence(
        agents.confidence_agent(error_msg, str(analysis_text or ""), fixed_code),
        default=8 if fast_mode else 7,
    )
    if fix_verification:
        confidence = min(10, confidence + 1) if fix_verification["resolved"] else max(1, confidence - 2)

    verification_parts = [orchestration_result.get("path_taken") or analysis_data.get("status")]
    if fix_verification:
        verification_parts.append(
            "Sandbox verification passed."
            if fix_verification["resolved"]
            else f"Sandbox verification failed: {fix_verification['error']}"
        )

    response = DebugResponse(
        success=False,
        error=error_msg,
        details=None,
        analysis=analysis_text,
        explanation=explanation_text,
        verification=" ".join(part for part in verification_parts if part),
        fixed_code=fixed_code,
        severity=severity,
        confidence=confidence,
        complexity=complexity,
        security_audit=security_data,
        beginner_explanation=(
            explanation_text
            or f"{execution.error_type or 'RuntimeError'} interrupted execution and needs a targeted fix."
        ),
        learning_tips=_build_learning_tips(execution.error_type, execution.timed_out),
        error_concept=execution.error_type or ("Timeout" if execution.timed_out else "RuntimeError"),
        metrics={
            "scan_rag": float(p1_time),
            "viper_orchestration": float(p2_time),
            "final_synthesis": 0.0,
            "execution": float(execution.duration),
            "fast_mode": 1.0 if fast_mode else 0.0,
            "cache_status": 0.0,
        },
        total_time=round(time.time() - grand_start, 3),
        source_path=response_source_path,
        source_code=code_text,
        pipeline_mode=pipeline_mode,
        stdout=execution.stdout,
        stderr=execution.stderr,
        exit_code=execution.exit_code,
        timed_out=execution.timed_out,
        error_line=execution.error_line,
        error_type=execution.error_type,
        execution_backend=execution.backend,
    )

    if cache_key:
        debug_cache.set(cache_key, response)
    return response


async def _run_debug_pipeline_limited(
    path: Path,
    mode: str | None,
    agents,
    scanner,
    rag,
    debug_cache,
    analysis_cache,
    semaphore,
) -> DebugResponse:
    async with semaphore:
        return await _run_debug_pipeline(path, mode, agents, scanner, rag, debug_cache, analysis_cache)


@router.post("/debug", response_model=DebugResponse)
async def debug_file(
    request: DebugRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
    semaphore=Depends(get_pipeline_semaphore),
):
    file_path = _safe_resolve_workspace_path(request.file_path, must_exist=True, enforce_python=True)
    return await _run_debug_pipeline_limited(
        file_path,
        request.mode,
        agents,
        scanner,
        rag,
        debug_cache,
        analysis_cache,
        semaphore,
    )


async def _run_debug_pipeline_streaming(
    task_id: str,
    path: Path,
    mode: str | None,
    agents,
    scanner,
    rag,
    debug_cache,
    analysis_cache,
    semaphore,
):
    bus = get_event_bus()

    try:
        bus.publish(task_id, EventType.STAGE, {
            "message": "Preparing runtime execution...",
            "stage": "runtime",
            "stage_index": 1,
            "total_stages": 4,
        })

        async with semaphore:
            bus.publish(task_id, EventType.STAGE, {
                "message": "Executing code inside the sandbox...",
                "stage": "execute",
                "stage_index": 2,
                "total_stages": 4,
            })
            response = await _run_debug_pipeline(
                path,
                mode,
                agents,
                scanner,
                rag,
                debug_cache,
                analysis_cache,
            )

        bus.publish(task_id, EventType.STAGE, {
            "message": response.success
            and "Execution completed without runtime errors."
            or "Runtime failure analyzed and patch prepared.",
            "stage": "analysis",
            "stage_index": 3,
            "total_stages": 4,
        })
        bus.publish(task_id, EventType.RESULT, {"result": response.model_dump()})
        bus.publish(task_id, EventType.COMPLETE, {
            "message": response.metrics and response.metrics.get("cache_status") == 1.0
            and "Debug complete (analysis cache hit)."
            or "Debug pipeline complete.",
            "total_time": response.total_time,
        })
    except Exception as exc:
        logger.exception("Streaming pipeline failed for task %s", task_id)
        bus.publish(task_id, EventType.ERROR, {
            "message": f"Pipeline error: {exc}",
            "code": "PIPELINE_ERROR",
            "traceback": traceback.format_exc()[-2000:],
        })


@router.post("/debug_stream", status_code=202)
async def debug_file_stream(
    request: DebugRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
    semaphore=Depends(get_pipeline_semaphore),
):
    from backend.config import USE_DISTRIBUTED

    file_path = _safe_resolve_workspace_path(request.file_path, must_exist=True, enforce_python=True)

    task_id = str(uuid.uuid4())
    bus = get_event_bus()
    bus.publish(task_id, EventType.STAGE, {
        "message": "Initializing debug pipeline...",
        "stage": "init",
        "stage_index": 0,
        "total_stages": 4,
    })

    dispatch_mode = get_event_bus_mode()

    if USE_DISTRIBUTED and dispatch_mode == "redis":
        from backend.tasks import run_debug_pipeline

        run_debug_pipeline.apply_async(
            args=[task_id, str(file_path), request.mode],
            task_id=task_id,
            queue="debug",
        )
        logger.info("Dispatched task %s to Celery queue 'debug'", task_id)
    else:
        asyncio.create_task(
            _run_debug_pipeline_streaming(
                task_id,
                file_path,
                request.mode,
                agents,
                scanner,
                rag,
                debug_cache,
                analysis_cache,
                semaphore,
            )
        )
        logger.info("Dispatched task %s via asyncio.create_task (local mode)", task_id)

    return JSONResponse(
        status_code=202,
        content={
            "task_id": task_id,
            "stream_url": f"/stream/{task_id}",
            "status_url": f"/task/{task_id}",
            "result_url": f"/task/{task_id}/result",
            "dispatch_mode": dispatch_mode,
        },
    )


@router.post("/analyze_complexity")
async def analyze_complexity(
    request: ComplexityRequest,
    agents=Depends(get_agents),
):
    return await run_in_executor(agents.complexity_agent, request.code)


async def _run_batch_debug_item(
    path_text: str,
    mode: str | None,
    agents,
    scanner,
    rag,
    debug_cache,
    analysis_cache,
    semaphore,
) -> dict[str, Any]:
    try:
        path = _safe_resolve_workspace_path(path_text, must_exist=True, enforce_python=True)
        result = await _run_debug_pipeline_limited(
            path,
            mode,
            agents,
            scanner,
            rag,
            debug_cache,
            analysis_cache,
            semaphore,
        )
        return {"ok": True, "path": str(path), "result": result.model_dump()}
    except Exception as exc:
        return {"ok": False, "path": path_text, "error": str(exc)}


@router.post("/debug_batch")
async def debug_batch(
    request: BatchDebugRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
):
    started = time.time()
    file_paths = [item.strip() for item in request.file_paths if item and item.strip()]
    if not file_paths:
        raise HTTPException(status_code=400, detail="file_paths must include at least one valid path.")

    bounded_concurrency = max(1, min(request.max_concurrency, PIPELINE_CONCURRENCY))
    batch_semaphore = asyncio.Semaphore(bounded_concurrency)

    async def _worker(path_text: str) -> dict[str, Any]:
        return await _run_batch_debug_item(
            path_text,
            request.mode,
            agents,
            scanner,
            rag,
            debug_cache,
            analysis_cache,
            batch_semaphore,
        )

    items = await asyncio.gather(*[_worker(path_text) for path_text in file_paths])
    succeeded = sum(1 for item in items if item.get("ok"))
    return {
        "requested": len(file_paths),
        "processed": len(items),
        "succeeded": succeeded,
        "failed": len(items) - succeeded,
        "duration_seconds": round(time.time() - started, 3),
        "mode": request.mode,
        "items": items,
    }


@router.post("/debug_snippet", response_model=DebugResponse)
async def debug_snippet(
    request: SnippetRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
    semaphore=Depends(get_pipeline_semaphore),
):
    if len(request.code) > MAX_SNIPPET_CHARS:
        raise HTTPException(status_code=413, detail=f"Snippet too large. Max {MAX_SNIPPET_CHARS} chars.")

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        dir=str(UPLOAD_DIR),
        prefix="_snippet_",
        encoding="utf-8",
    ) as tmp:
        tmp.write(request.code)
        tmp_path = Path(tmp.name)

    try:
        return await _run_debug_pipeline_limited(
            tmp_path,
            request.mode,
            agents,
            scanner,
            rag,
            debug_cache,
            analysis_cache,
            semaphore,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.post("/validate_fix")
async def validate_fix(
    request: ValidateFixRequest,
    agents=Depends(get_agents),
):
    clean_fixed = _sanitize_markdown_code(request.fixed)
    if not clean_fixed:
        raise HTTPException(status_code=400, detail="Fixed code is empty.")

    original_code = request.original
    fixed_valid, fixed_syntax_error = _syntax_check(clean_fixed)
    meaningful_change = fixed_valid and _fix_changes_behavior(original_code, clean_fixed)

    original_complexity, fixed_complexity = await asyncio.gather(
        run_in_executor(agents.complexity_agent, original_code),
        run_in_executor(agents.complexity_agent, clean_fixed),
    )

    ready_to_apply = fixed_valid and meaningful_change

    return {
        "ready_to_apply": ready_to_apply,
        "syntax": {
            "fixed_valid": fixed_valid,
            "error": fixed_syntax_error,
        },
        "quality_score": 95 if ready_to_apply else 10,
        "complexity_delta": int(fixed_complexity.get("complexity_score", 0))
        - int(original_complexity.get("complexity_score", 0)),
    }


@router.post("/apply_fix")
async def apply_fix(request: ApplyFixRequest):
    file_path = _safe_resolve_workspace_path(request.file_path, must_exist=True, enforce_python=True)
    clean_code = _sanitize_markdown_code(request.fixed_code)

    try:
        file_path.write_text(clean_code, encoding="utf-8")
        logger.info("applied fix to %s", file_path)
        return {"success": True, "path": str(file_path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    safe_name = _safe_upload_name(file.filename)
    workspace_upload_dir = (get_workspace_root() / ".viper_uploads").resolve()
    workspace_upload_dir.mkdir(parents=True, exist_ok=True)

    destination = workspace_upload_dir / safe_name
    if destination.exists():
        destination = workspace_upload_dir / (
            f"{destination.stem}_{int(time.time())}_{uuid.uuid4().hex[:8]}{destination.suffix}"
        )

    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Uploaded file is too large.")
        destination.write_bytes(content)
        return {
            "success": True,
            "path": str(destination),
            "filename": destination.name,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/diff")
async def get_diff(request: DiffRequest):
    diff_text = _generate_unified_diff(request.original, request.fixed)
    return {"diff": diff_text}
