import asyncio
import ast
import hashlib
import tempfile
import time
import traceback
import uuid
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
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


def _is_safe_patch(original: str, patched: str) -> bool:
    """AST-based structural guard: reject patches that delete unrelated top-level blocks."""
    try:
        old_tree = ast.parse(original)
        new_tree = ast.parse(patched)
    except SyntaxError:
        return False

    def _top_level_names(tree):
        names = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
        return names

    old_names = _top_level_names(old_tree)
    new_names = _top_level_names(new_tree)
    deleted_blocks = old_names - new_names
    # Allow removing at most 1 top-level block (could be the buggy one)
    return len(deleted_blocks) <= 1
from backend.services.sandbox import execute_code_string, execute_file
from backend.services.precheck import run_static_precheck, run_micro_execution
from backend.utils import (
    _generate_unified_diff,
    _safe_resolve_workspace_path,
    _safe_upload_name,
)

router = APIRouter(tags=["debug"])


def _cache_key(code: str, error: str) -> str:
    content = f"{code}!!{error}"
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def _syntax_check(code: str) -> tuple[bool, str | None]:
    """
    Perform a rapid, lightweight AST parse to validate Python syntax.
    
    Args:
        code (str): The raw code string to evaluate.
        
    Returns:
        tuple[bool, str | None]: A boolean indicating validity, and the exact SyntaxError message if false.
    """
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as syntax_exception:
        return False, str(syntax_exception)


def _sanitize_markdown_code(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if len(lines) > 2:
            return "\n".join(lines[1:-1])
    return clean


@lru_cache(maxsize=256)
def _ast_signature(code: str) -> str | None:
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None
    return ast.dump(parsed, annotate_fields=False, include_attributes=False)


# Memoized syntax check to avoid repeated parsing in validate_fix flows
@lru_cache(maxsize=128)
def _syntax_check_cached(code: str) -> tuple[bool, str | None]:
    return _syntax_check(code)


def _fix_changes_behavior(original_code: str, fixed_code: str) -> bool:
    """
    Determine if a generated patch actually alters the logic of the code using AST signatures.
    Prevents the system from suggesting semantic no-ops (e.g., just adding comments or spaces).
    
    Args:
        original_code (str): The pre-patch source text.
        fixed_code (str): The post-patch source text to verify.
        
    Returns:
        bool: True if the AST graph is distinctly different; False if it is a structural no-op.
    """
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
    """
    Micro-execution pipeline: Runs the newly patched code in an isolated temporary harness
    to ensure the fix didn't introduce secondary syntax errors or immediately crash.
    
    Args:
        path (Path): Path of the original failing file to preserve suffix logic.
        fixed_code (str): The generated code patch to evaluate.
        
    Returns:
        dict: Standardized metadata payload detailing success, exit_codes, and tracebacks.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=path.suffix or ".py",
        delete=False,
        dir=str(UPLOAD_DIR),
        prefix="_verified_fix_",
        encoding="utf-8",
    ) as temp_scratchpad:
        temp_scratchpad.write(fixed_code)
        verification_path = Path(temp_scratchpad.name)

    try:
        execution = execute_file(str(verification_path))
        
        execution_success = (
            execution.exit_code == 0
            and not execution.timed_out
            and not execution.stderr.strip()
        )
        
        error_msg = _execution_error_message(
            verification_path,
            execution.stdout,
            execution.stderr,
            execution.exit_code,
            execution.timed_out,
        )
        return {
            "resolved": execution_success,
            "error": error_msg,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "exit_code": execution.exit_code,
            "timed_out": execution.timed_out,
            "error_type": execution.error_type,
            "backend": execution.backend,
        }
    finally:
        if verification_path.exists():
            verification_path.unlink()


def _build_standard_response(
    *,
    success: bool,
    error: str | None = None,
    details: str | None = None,
    analysis: str | None = None,
    explanation: str | None = None,
    verification: str | None = None,
    fixed_code: str | None = None,
    severity: str | None = None,
    confidence: int | None = None,
    complexity: dict | None = None,
    security_audit: dict | None = None,
    beginner_explanation: str | None = None,
    learning_tips: list[str] | None = None,
    error_concept: str | None = None,
    metrics: dict | None = None,
    total_time: float | None = None,
    source_path: str | None = None,
    source_code: str | None = None,
    pipeline_mode: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    exit_code: int | None = None,
    timed_out: bool | None = None,
    error_line: int | None = None,
    error_type: str | None = None,
    execution_backend: str | None = None,
) -> DebugResponse:
    metrics = metrics or {
        "scan_rag": 0.0,
        "viper_orchestration": 0.0,
        "final_synthesis": 0.0,
        "execution": 0.0,
        "fast_mode": 1.0 if pipeline_mode == "fast" else 0.0,
        "is_preliminary": 1.0 if execution_backend == "precheck" else 0.0,
        "cache_status": 0.0,
    }
    loc = len(source_code.splitlines()) if source_code else 0
    complexity = complexity or {"grade": "N/A", "functions": 0, "classes": 0, "loops": 0, "conditions": 0, "loc": loc}
    learning_tips = learning_tips or []
    
    return DebugResponse(
        success=success,
        error=error,
        details=details,
        analysis=analysis,
        explanation=explanation,
        verification=verification,
        fixed_code=fixed_code,
        severity=severity or "INFO",
        confidence=confidence or 10,
        complexity=complexity,
        security_audit=security_audit,
        topology=None,
        beginner_explanation=beginner_explanation,
        learning_tips=learning_tips,
        error_concept=error_concept,
        metrics=metrics,
        total_time=total_time or 0.0,
        source_path=source_path,
        source_code=source_code,
        pipeline_mode=pipeline_mode,
        stdout=stdout or "",
        stderr=stderr or "",
        exit_code=exit_code or 0,
        timed_out=timed_out or False,
        error_line=error_line or 0,
        error_type=error_type,
        execution_backend=execution_backend,
    )

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
    return _build_standard_response(
        success=False,
        error="Model inference failed",
        details=str(exc),
        analysis="The code execution failure was captured, but the AI model could not generate a valid fix.",
        explanation="Check the model configuration, prompt output, or local runtime and try again.",
        verification="Model inference failed before a verified patch could be produced.",
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
        
    has_stderr = bool(stderr.strip())
    
    if exit_code == 0 and not has_stderr:
        return None
        
    error_text = stderr.strip() if has_stderr else stdout.strip()
    
    if exit_code != 0 and not error_text:
        return f"Execution failed for {path.name} with exit code {exit_code}."
        
    # Context Sanity Filter: Strip internal dependencies from traceback
    filtered_lines = []
    for line in error_text.splitlines():
        if "site-packages" not in line and "/usr/lib/python" not in line and "<frozen " not in line:
            filtered_lines.append(line)
            
    final_err = "\n".join(filtered_lines).strip()
    if not final_err:
        final_err = error_text
        
    return final_err


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



# Precompiled patterns for traceback pruning (avoids re-compilation per call)
_INTERNAL_FRAME_TOKENS = frozenset({'site-packages', 'importlib', '/usr/local/lib', 'lib/python'})


def _prune_traceback(tb_str: str) -> str:
    """Filter out non-user-relevant internal Python frames to reduce LLM context."""
    if not tb_str:
        return tb_str
    lines = tb_str.splitlines()
    pruned = []
    for line in lines:
        if any(token in line for token in _INTERNAL_FRAME_TOKENS):
            continue
        pruned.append(line)

    # Deduplicate massive recurrent frames (e.g. RecursionError)
    if len(pruned) > 50:
        pruned = pruned[:25] + ["... [Frames Truncated for Context Optimization] ..."] + pruned[-25:]

    return chr(10).join(pruned)


def _minify_code_context(code_text: str) -> str:
    """Strip comments, docstrings, and blank lines. Never truncate structurally."""
    lines = []
    in_docstring = False
    for line in code_text.splitlines():
        stripped = line.strip()
        if '"""' in stripped or "'''" in stripped:
            if stripped.count('"""') % 2 == 1 or stripped.count("'''") % 2 == 1:
                in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith('#') or not stripped:
            continue
        lines.append(line)

    return chr(10).join(lines)

def _extract_error_context(code_text: str, error_line: int | None) -> tuple[str | None, int, int]:
    if not error_line: return None, -1, -1
    try:
        tree = ast.parse(code_text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    if node.lineno <= error_line <= node.end_lineno:
                        lines = code_text.splitlines()
                        return chr(10).join(lines[node.lineno-1:node.end_lineno]), node.lineno, node.end_lineno
    except Exception: pass
    return None, -1, -1

async def _run_debug_pipeline(
    path: Path,
    mode: str | None,
    agents,
    scanner,
    rag,
    debug_cache,
    analysis_cache,
    task_id: str | None = None,
    request: Request | None = None,
) -> DebugResponse:
    from backend.services.precheck import run_static_precheck

    grand_start = time.time()
    path_text = str(path)
    pipeline_mode = mode or ("fast" if FAST_MODE_DEFAULT else "full")
    fast_mode = pipeline_mode == "fast"

    try:
        raw_code = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="File could not be read.") from exc

    # Initial execution just to set up baseline and cache
    execution = await run_in_executor(execute_file, path_text)
    
    execution_success = (
        execution.exit_code == 0
        and not execution.timed_out
        and not execution.stderr.strip()
    )
    
    error_msg = _execution_error_message(path, execution.stdout, execution.stderr, execution.exit_code, execution.timed_out)
    response_source_path = _source_path_for_response(path)
    max_iterations = 6
    
    # Cache hit logic
    if not execution_success:
        cache_signature = f"{error_msg}|line={execution.error_line}|type={execution.error_type}|mode={pipeline_mode}|iters={max_iterations}"
        cache_key = f"{_cache_key(raw_code, cache_signature)}:v2"
        cached = debug_cache.get(cache_key)
        if cached:
            result = cached.model_copy(deep=True)
            result.total_time = round(time.time() - grand_start, 3)
            result.metrics = {**(result.metrics or {}), "cache_status": 1.0}
            return result
    else:
        cache_key = None

    analytics_task = _get_cached_code_analytics(raw_code, agents, analysis_cache, include_security=(not fast_mode) and ENABLE_SECURITY_AUDIT)

    if execution_success:
        assert execution.exit_code == 0, "Invalid success state: exit_code != 0"
        complexity, security_data = await analytics_task
        metrics = {"execution": float(execution.duration), "fast_mode": 1.0 if fast_mode else 0.0, "cache_status": 0.0, "is_preliminary": 0.0, "scan_rag": 0.0, "viper_orchestration": 0.0, "final_synthesis": 0.0}
        return _build_standard_response(
            success=True,
            explanation="Execution completed successfully.",
            verification=f"Runtime completed with exit code 0 via {execution.backend}.",
            severity="INFO",
            confidence=10,
            complexity=complexity,
            security_audit=security_data,
            beginner_explanation="The program ran without raising an exception.",
            metrics=metrics,
            total_time=round(time.time() - grand_start, 3),
            source_path=response_source_path,
            source_code=raw_code,
            pipeline_mode=pipeline_mode,
            stdout=execution.stdout,
            stderr=execution.stderr,
            exit_code=execution.exit_code,
            timed_out=execution.timed_out,
            error_line=execution.error_line,
            error_type=execution.error_type,
            execution_backend=execution.backend,
        )

    # Begin Iterative Repair
    current_code = raw_code
    iteration = 0
    accumulated_history = []
    final_success = False
    
    original_execution = execution
    last_exec = execution
    last_error_msg = error_msg
    
    seen_errors = set()
    code_history = {raw_code}
    force_7b = False
    _minify_cache = {}
    consecutive_7b_failures = 0

    p2_start = time.time()
    
    while iteration < max_iterations:
        if request and await request.is_disconnected():
            accumulated_history.append("! Client disconnected. Aborting pipeline.")
            break
            
        if iteration >= 3:
            force_7b = True  # Adaptive routing bypasses fast model on deep iterations
        
        iteration += 1
        
        try:
            def get_minify(c):
                ch = hash(c)
                if ch not in _minify_cache:
                    _minify_cache[ch] = agents.strip_unused_imports(c) if hasattr(agents, 'strip_unused_imports') else _minify_code_context(c)
                return _minify_cache[ch]
                
            static_err_t = run_in_executor(run_static_precheck, current_code)
            minified_t = run_in_executor(get_minify, current_code)
            static_err, context_code = await asyncio.gather(static_err_t, minified_t)
        except Exception:
            static_err = await run_in_executor(run_static_precheck, current_code)
            context_code = agents.strip_unused_imports(current_code) if hasattr(agents, 'strip_unused_imports') else _minify_code_context(current_code)
        
        if static_err and not force_7b:
            last_error_msg = static_err["msg"]
            if task_id:
                get_event_bus().publish(task_id, EventType.PROGRESS, {"message": f"⚡ Fixing {static_err.get('error_type', 'SyntaxError')}..."})
            if last_error_msg in seen_errors:
                force_7b = True
                iteration -= 1  # Don't waste an iteration if we're just escalating
                continue
            
            seen_errors.add(last_error_msg)
            try:
                err_line = static_err.get("line")
                snippet, start_l, end_l = _extract_error_context(current_code, err_line)
                if snippet:
                    fixed_snippet = await run_in_executor(agents.code_fixer_agent, snippet, last_error_msg, 1, "1.5B")
                    lines = current_code.splitlines()
                    fixed_candidate = chr(10).join(lines[:start_l-1] + fixed_snippet.splitlines() + lines[end_l:])
                else:
                    fixed_candidate = await run_in_executor(agents.code_fixer_agent, context_code, last_error_msg, 1, "1.5B")
                
                # Diff & Patch Validation
                try:
                    ast.parse(fixed_candidate)
                except SyntaxError:
                    force_7b = True
                    iteration -= 1  # Don't waste iteration on 1.5B syntax failure
                    accumulated_history.append(f"! [1.5B] Rejected static fix (introduced SyntaxError). Escalating to 7B.")
                    continue
                    
                if fixed_candidate in code_history:
                    force_7b = True
                    accumulated_history.append(f"! [1.5B] Rejected static fix (reverted to previous state)")
                    continue
                    
                line_diff = abs(len(fixed_candidate.splitlines()) - len(current_code.splitlines()))
                if line_diff > max(20, len(current_code.splitlines()) * 0.5):
                    force_7b = True
                    accumulated_history.append(f"! [1.5B] Rejected static fix (drastic structural deletion, diff={line_diff})")
                    continue
                    
                if not _is_safe_patch(current_code, fixed_candidate):
                    force_7b = True
                    accumulated_history.append(f"! AI-generated fix was blocked due to unsafe structural changes")
                    continue
                
                accumulated_history.append(f"✓ [1.5B] Fixed static {static_err['error_type']} at line {static_err.get('line', '?')}")
                current_code = fixed_candidate
                code_history.add(current_code)
            except Exception:
                break
        else:
            if fast_mode:
                last_exec = await run_in_executor(execute_code_string, current_code)
            else:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as tmp:
                    tmp.write(current_code)
                    tmp_path = tmp.name
                last_exec = await run_in_executor(execute_file, tmp_path)
                os.unlink(tmp_path)
            
            last_error_msg = _execution_error_message(path, last_exec.stdout, last_exec.stderr, last_exec.exit_code, last_exec.timed_out)
            if last_error_msg:
                last_error_msg = last_error_msg[-1200:] # Token minimization
                if task_id:
                    get_event_bus().publish(task_id, EventType.PROGRESS, {"message": f"⚡ Resolving {last_exec.error_type or 'Runtime error'}..."})
            force_7b = False
            
            if last_error_msg is None:
                final_success = True
                break
                
            if last_error_msg in seen_errors:
                accumulated_history.append(f"! Escalating stuck runtime error to 7B reasoning.")
            seen_errors.add(last_error_msg)
                
            try:
                # context_code is already mapped correctly above using gather
                
                local_knowledge = ""
                if not fast_mode:
                    local_knowledge = await run_in_executor(rag.query_docs, last_error_msg[-2000:])
                
                analysis_data = await run_in_executor(
                    agents.multi_agent_pipeline, last_error_msg, context_code, local_knowledge, "7B"
                )
                
                err_line = last_exec.error_line
                snippet, start_l, end_l = _extract_error_context(current_code, err_line)
                if snippet:
                    fixed_snippet = await run_in_executor(agents.code_fixer_agent, snippet, last_error_msg, 1, "7B")
                    lines = current_code.splitlines()
                    fixed_candidate = chr(10).join(lines[:start_l-1] + fixed_snippet.splitlines() + lines[end_l:])
                else:
                    fixed_candidate = await run_in_executor(agents.code_fixer_agent, context_code, last_error_msg, 1, "7B")
                
                # Diff & Patch Validation
                try:
                    ast.parse(fixed_candidate)
                except SyntaxError:
                    consecutive_7b_failures += 1
                    accumulated_history.append(f"! [7B] Rejected fix (introduced SyntaxError)")
                    if consecutive_7b_failures >= 2:
                        accumulated_history.append("! 7B model failed consecutively. Terminating loop.")
                        break
                    continue
                    
                if fixed_candidate in code_history:
                    accumulated_history.append(f"! [7B] Rejected fix (reverted to previous state). Terminating loop.")
                    break
                    
                line_diff = abs(len(fixed_candidate.splitlines()) - len(current_code.splitlines()))
                if line_diff > max(20, len(current_code.splitlines()) * 0.5):
                    accumulated_history.append(f"! [7B] Rejected fix (drastic structural deletion, diff={line_diff})")
                    continue
                    
                if not _is_safe_patch(current_code, fixed_candidate):
                    accumulated_history.append(f"! AI-generated fix was blocked due to unsafe structural changes")
                    continue
                
                desc = analysis_data.get('explanation', last_exec.error_type or 'Runtime error')
                consecutive_7b_failures = 0  # Reset on success
                accumulated_history.append(f"✓ [7B] Resolved {last_exec.error_type}: {desc[:60]}...")
                current_code = fixed_candidate
                code_history.add(current_code)
            except Exception as e:
                break
                
    p2_time = round(time.time() - p2_start, 3)
    complexity, security_data = await analytics_task
    severity = await run_in_executor(agents.severity_agent, last_error_msg or error_msg)

    # Final Sandbox check of the produced code if we produced anything
    if current_code != raw_code and not final_success:
        async def _run_final():
            if fast_mode:
                return await run_in_executor(execute_code_string, current_code)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as tmp:
                tmp.write(current_code)
                tmp_path = tmp.name
            ex = await run_in_executor(execute_file, tmp_path)
            os.unlink(tmp_path)
            return ex

        final_exec_1 = await _run_final()
        final_exec_2 = await _run_final()
        
        final_error_1 = _execution_error_message(path, final_exec_1.stdout, final_exec_1.stderr, final_exec_1.exit_code, final_exec_1.timed_out)
        final_error_2 = _execution_error_message(path, final_exec_2.stdout, final_exec_2.stderr, final_exec_2.exit_code, final_exec_2.timed_out)
        
        both_clean = final_error_1 is None and final_error_2 is None
        outputs_match = final_exec_1.stdout == final_exec_2.stdout
        
        if both_clean and outputs_match:
            final_success = True
        elif both_clean and not outputs_match:
            # Non-deterministic but valid (e.g. datetime, random, uuid)
            final_success = True
            accumulated_history.append("✓ Final validation passed (dynamic output detected, both runs error-free).")
        else:
            final_success = False
            accumulated_history.append("! Final validation: errors persist after patching.")
        execution = final_exec_1

    final_fixed_code = current_code if current_code != raw_code else None

    # Format the analysis
    formatted_analysis = "\\n".join(accumulated_history) if accumulated_history else "Iterative analysis attempted..."

    metrics = {
        "scan_rag": 0.0,
        "viper_orchestration": float(p2_time),
        "final_synthesis": 0.0,
        "execution": float(original_execution.duration),
        "fast_mode": 1.0 if fast_mode else 0.0,
        "cache_status": 0.0,
        "is_preliminary": 0.0,
    }
    response = _build_standard_response(
        success=False, # The original script had an error
        error=error_msg,
        analysis=formatted_analysis,
        explanation=f"Applied {len(accumulated_history)} multi-stage fixes via 1.5B/7B orchestrator." if accumulated_history else "Analysis failed to produce iterative stages.",
        verification="Sandbox verification passed in iteration." if final_success else "Errors remain after iterative sandbox limits.",
        fixed_code=final_fixed_code,
        severity=severity,
        confidence=10 if final_success else 4,
        complexity=complexity,
        security_audit=security_data,
        beginner_explanation="The script crashed initially safely handling iterative faults via the dual-model system.",
        learning_tips=_build_learning_tips(original_execution.error_type, original_execution.timed_out),
        error_concept=original_execution.error_type or "RuntimeError",
        metrics=metrics,
        total_time=round(time.time() - grand_start, 3),
        source_path=response_source_path,
        source_code=raw_code,
        pipeline_mode=pipeline_mode,
        stdout=original_execution.stdout,
        stderr=original_execution.stderr,
        exit_code=original_execution.exit_code,
        timed_out=original_execution.timed_out,
        error_line=original_execution.error_line,
        error_type=original_execution.error_type,
        execution_backend=original_execution.backend,
    )

    if cache_key and final_fixed_code:
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
    task_id: str | None = None,
    request: Request | None = None
) -> DebugResponse:
    async with semaphore:
        return await _run_debug_pipeline(path, mode, agents, scanner, rag, debug_cache, analysis_cache, task_id=task_id, request=request)


@router.post("/pre_check", response_model=DebugResponse)
async def pre_check_file(
    request: DebugRequest,
    debug_cache=Depends(get_debug_cache),
):
    """Zero-latency static check + micro-execution. Returns preliminary insight instantly."""
    
    file_path = await asyncio.to_thread(_safe_resolve_workspace_path, request.file_path, must_exist=True, enforce_python=True)
    
    try:
        raw_code = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="replace")
    except OSError:
        raise HTTPException(status_code=404, detail="File could not be read.")

    # 1. Heavily cached fast-path
    mode_str = request.mode or "default"
    digest = hashlib.sha256(f"{raw_code}:{mode_str}".encode("utf-8", errors="ignore")).hexdigest()
    cache_key = f"pipeline:{digest}"
    cached = debug_cache.get(cache_key)
    if cached:
        cached.metrics["cache_status"] = 1.0
        return cached

    # 2. Static Analysis
    static_err = await run_in_executor(run_static_precheck, raw_code)
    err_data = static_err

    # 3. Micro Execution (if no static error)
    if not err_data:
        err_data = await run_in_executor(run_micro_execution, raw_code)
        
    start_time = time.time()
    
    if err_data:
        metrics = {
            "scan_rag": 0.0,
            "viper_orchestration": 0.0,
            "final_synthesis": 0.0,
            "execution": 0.1,
            "fast_mode": 1.0,
            "is_preliminary": 1.0,
            "cache_status": 0.0,
        }
        resp = _build_standard_response(
            success=False,
            error=err_data["msg"],
            analysis="Preliminary static/micro-execution check found an immediate error.",
            explanation=err_data["msg"],
            verification="Caught prior to deep LLM analysis.",
            severity="CRITICAL",
            confidence=10,
            beginner_explanation=f"A basic {err_data['error_type']} was detected before full execution.",
            learning_tips=_build_learning_tips(err_data["error_type"], False),
            error_concept=err_data["error_type"],
            metrics=metrics,
            total_time=round(time.time() - start_time, 3),
            source_path=_source_path_for_response(file_path),
            source_code=raw_code,
            pipeline_mode="fast",
            stderr=err_data["msg"],
            exit_code=1,
            error_line=err_data.get("line", 1),
            error_type=err_data["error_type"],
            execution_backend="precheck"
        )
    else:
        # No errors found in pre-check, we yield a success skeleton
        # that will be overwritten if the full pipeline finds something deep.
        metrics = {
            "execution": 0.1, "is_preliminary": 1.0, "cache_status": 0.0,
            "scan_rag": 0.0, "viper_orchestration": 0.0, "final_synthesis": 0.0, "fast_mode": 1.0
        }
        resp = _build_standard_response(
            success=True,
            analysis="Pre-check passed successfully.",
            explanation="Initial scan clean. Running deep sandbox execution...",
            verification="Waiting for full backend finish.",
            severity="INFO",
            confidence=10,
            beginner_explanation="The code looks structurally sound so far.",
            metrics=metrics,
            total_time=round(time.time() - start_time, 3),
            source_path=_source_path_for_response(file_path),
            source_code=raw_code,
            pipeline_mode="fast",
            execution_backend="precheck"
        )

    debug_cache.set(cache_key, resp)
    return resp


@router.post("/debug", response_model=DebugResponse)
async def debug_file(
    request: Request,
    body: DebugRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
    semaphore=Depends(get_pipeline_semaphore),
):
    file_path = _safe_resolve_workspace_path(body.file_path, must_exist=True, enforce_python=True)
    return await _run_debug_pipeline_limited(
        file_path,
        body.mode,
        agents,
        scanner,
        rag,
        debug_cache,
        analysis_cache,
        semaphore,
        request=request,
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
    request: Request | None = None,
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
                task_id=task_id,
                request=request,
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
    request: Request,
    body: DebugRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
    semaphore=Depends(get_pipeline_semaphore),
):
    from backend.config import USE_DISTRIBUTED

    file_path = _safe_resolve_workspace_path(body.file_path, must_exist=True, enforce_python=True)

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
            args=[task_id, str(file_path), body.mode],
            task_id=task_id,
            queue="debug",
        )
        logger.info("Dispatched task %s to Celery queue 'debug'", task_id)
    else:
        asyncio.create_task(
            _run_debug_pipeline_streaming(
                task_id,
                file_path,
                body.mode,
                agents,
                scanner,
                rag,
                debug_cache,
                analysis_cache,
                semaphore,
                request=request,
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
    request: Request,
    body: BatchDebugRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
):
    started = time.time()
    file_paths = [item.strip() for item in body.file_paths if item and item.strip()]
    if not file_paths:
        raise HTTPException(status_code=400, detail="file_paths must include at least one valid path.")

    bounded_concurrency = max(1, min(body.max_concurrency, PIPELINE_CONCURRENCY))
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
        "mode": body.mode,
        "items": items,
    }


@router.post("/debug_snippet", response_model=DebugResponse)
async def debug_snippet(
    request: Request,
    body: SnippetRequest,
    agents=Depends(get_agents),
    scanner=Depends(get_scanner),
    rag=Depends(get_rag),
    debug_cache=Depends(get_debug_cache),
    analysis_cache=Depends(get_analysis_cache),
    semaphore=Depends(get_pipeline_semaphore),
):
    if len(body.code) > MAX_SNIPPET_CHARS:
        raise HTTPException(status_code=413, detail=f"Snippet too large. Max {MAX_SNIPPET_CHARS} chars.")

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        dir=str(UPLOAD_DIR),
        prefix="_snippet_",
        encoding="utf-8",
    ) as tmp:
        tmp.write(body.code)
        tmp_path = Path(tmp.name)

    try:
        return await _run_debug_pipeline_limited(
            tmp_path,
            body.mode,
            agents,
            scanner,
            rag,
            debug_cache,
            analysis_cache,
            semaphore,
            request=request,
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
    fixed_valid, fixed_syntax_error = _syntax_check_cached(clean_fixed)
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
