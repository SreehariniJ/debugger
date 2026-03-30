"""
tasks.py — Celery tasks for the debug pipeline.

These tasks run in a SEPARATE PROCESS from FastAPI. They use the
sync Redis publish() to send real-time updates that the FastAPI
SSE endpoint subscribes to.

Start the worker:
    celery -A backend.celery_app worker --loglevel=info --pool=solo -Q debug
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import traceback
import logging
from pathlib import Path

from backend.celery_app import celery_app
from backend.config import (
    FAST_MODE_DEFAULT, ENABLE_SECURITY_AUDIT, MODEL_PATH,
    WORKSPACE_ROOT, SCAN_CACHE_TTL_SECONDS, logger,
)

logger = logging.getLogger("offline_debugger.tasks")


def _cache_key(code: str, error: str) -> str:
    content = f"{code}!!{error}"
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


@celery_app.task(
    name="backend.tasks.run_debug_pipeline",
    bind=True,
    max_retries=1,
    soft_time_limit=120,
    time_limit=150,
)
def run_debug_pipeline(self, task_id: str, file_path: str, mode: str | None = None):
    """
    Celery task that executes the full debug pipeline and publishes
    real-time SSE events via Redis Pub/Sub.

    This runs in a Celery worker process — NOT in FastAPI.
    All LLM inference, scanning, and analysis happens here.
    """
    from backend.services.redis_event_bus import get_redis_event_bus
    from backend.services.event_bus import EventType

    bus = get_redis_event_bus()

    try:
        grand_start = time.time()
        path = Path(file_path).resolve()
        pipeline_mode = mode or ("fast" if FAST_MODE_DEFAULT else "full")

        bus.publish(task_id, EventType.STAGE, {
            "message": "Initializing model-backed debug pipeline...",
            "stage": "init",
            "stage_index": 1,
            "total_stages": 3,
        })

        from backend.dependencies import (
            get_agents,
            get_analysis_cache,
            get_debug_cache,
            get_rag,
            get_scanner,
        )
        from backend.routers.debug import _run_debug_pipeline

        agents = get_agents()
        scanner = get_scanner()
        rag = get_rag()
        debug_cache = get_debug_cache()
        analysis_cache = get_analysis_cache()

        bus.publish(task_id, EventType.STAGE, {
            "message": "Executing code and generating a verified AI fix...",
            "stage": "debug",
            "stage_index": 2,
            "total_stages": 3,
        })

        response = asyncio.run(
            _run_debug_pipeline(
                path,
                pipeline_mode,
                agents,
                scanner,
                rag,
                debug_cache,
                analysis_cache,
            )
        )
        result_payload = response.model_dump()

        bus.publish(task_id, EventType.STAGE, {
            "message": "Building final response...",
            "stage": "finalize",
            "stage_index": 3,
            "total_stages": 3,
        })
        bus.publish(task_id, EventType.RESULT, {"result": result_payload})
        bus.publish(task_id, EventType.COMPLETE, {
            "message": "Debug pipeline complete.",
            "total_time": round(time.time() - grand_start, 3),
        })
        return result_payload
        fast_mode = (pipeline_mode == "fast")

        # ── Stage 1: Reading file ───────────────────────────────────
        bus.publish(task_id, EventType.STAGE, {
            "message": "Reading source file...",
            "stage": "read_file",
            "stage_index": 1,
            "total_stages": 6,
        })

        try:
            code_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            bus.publish(task_id, EventType.ERROR, {
                "message": f"File could not be read: {exc}",
                "code": "FILE_READ_ERROR",
            })
            return {"success": False, "error": str(exc)}

        error_msg = f"Auto-analysis for {path.name}"

        # ── Stage 2: Initialize services (lazy in worker) ───────────
        bus.publish(task_id, EventType.STAGE, {
            "message": "Initializing AI agents & scanner...",
            "stage": "init_services",
            "stage_index": 2,
            "total_stages": 6,
        })

        # Import and instantiate services inside the worker
        from scanner import CodeScanner
        from rag_engine import LocalRAGEngine
        from agents import DebuggingAgents

        scanner = CodeScanner(str(WORKSPACE_ROOT), scan_cache_ttl_seconds=SCAN_CACHE_TTL_SECONDS)
        rag = LocalRAGEngine(data_dir="knowledge_base")
        agents = DebuggingAgents(model_path=MODEL_PATH)

        # ── Stage 3: Context & Knowledge ────────────────────────────
        bus.publish(task_id, EventType.STAGE, {
            "message": "Gathering context & querying knowledge base...",
            "stage": "context_knowledge",
            "stage_index": 3,
            "total_stages": 6,
        })

        path_text = str(path)
        code_context = scanner.get_context_for_file(path_text)
        local_knowledge = rag.query_docs(error_msg)
        severity = agents.severity_agent(error_msg)

        include_security = (not fast_mode) and ENABLE_SECURITY_AUDIT
        complexity = agents.complexity_agent(code_text)
        security_data = None
        if include_security:
            security_data = agents.security_audit_agent(code_text)

        # ── Stage 4: Fix Generation ─────────────────────────────────
        bus.publish(task_id, EventType.STAGE, {
            "message": "AI agents generating fix..." if not fast_mode else "Fast mode: generating quick fix...",
            "stage": "fix_generation",
            "stage_index": 4,
            "total_stages": 6,
        })

        if agents.llm is None:
            orchestration_result = {
                "success": False, "fix": "",
                "reason": "Model unavailable", "path_taken": "fallback",
            }
        elif fast_mode:
            quick_fix = agents.code_fixer_agent(code_context or code_text, error_msg, max_retries=1)
            orchestration_result = {
                "success": bool(quick_fix), "fix": quick_fix,
                "path_taken": "Fast mode generation",
            }
        else:
            workspace_files = scanner.scan_workspace()
            # viper_orchestration is async in the original, but we call sync here
            orchestration_result = agents.multi_strategy_fix(
                error_msg, code_context or code_text, workspace_files
            ) if hasattr(agents, 'multi_strategy_fix') else {
                "success": False, "fix": agents.code_fixer_agent(
                    code_context or code_text, error_msg, max_retries=2
                ), "path_taken": "Standard fix generation",
            }

        # ── Stage 5: Multi-Agent Synthesis ──────────────────────────
        bus.publish(task_id, EventType.STAGE, {
            "message": "Running multi-agent analysis synthesis...",
            "stage": "synthesis",
            "stage_index": 5,
            "total_stages": 6,
        })

        analysis_data = agents.multi_agent_pipeline(error_msg, code_context or code_text, local_knowledge)
        fixed_code = orchestration_result.get("fix")

        if fast_mode:
            confidence = 95
            edu = {
                "beginner_explanation": "A quick fix was applied in fast mode.",
                "learning_tips": [],
                "error_concept": "Fast Mode Patch",
            }
        else:
            confidence = agents.confidence_agent(
                error_msg, str(analysis_data.get("analysis", "")), fixed_code
            )
            edu = agents.beginner_explain_agent(
                error_msg, str(analysis_data.get("analysis", "")), fixed_code
            )

        # ── Stage 6: Finalize ───────────────────────────────────────
        bus.publish(task_id, EventType.STAGE, {
            "message": "Building final response...",
            "stage": "finalize",
            "stage_index": 6,
            "total_stages": 6,
        })

        p_total = round(time.time() - grand_start, 3)

        result_payload = {
            "success": True,
            "error": None,
            "analysis": analysis_data.get("analysis"),
            "explanation": analysis_data.get("explanation"),
            "verification": orchestration_result.get("path_taken"),
            "fixed_code": fixed_code,
            "severity": severity,
            "confidence": confidence,
            "complexity": complexity,
            "security_audit": security_data,
            "beginner_explanation": edu.get("beginner_explanation"),
            "learning_tips": edu.get("learning_tips"),
            "error_concept": edu.get("error_concept"),
            "metrics": {"fast_mode": 1.0 if fast_mode else 0.0},
            "total_time": p_total,
            "source_path": path_text,
            "pipeline_mode": pipeline_mode,
        }

        # Publish final result + completion
        bus.publish(task_id, EventType.RESULT, {"result": result_payload})
        bus.publish(task_id, EventType.COMPLETE, {
            "message": "Debug pipeline complete.",
            "total_time": p_total,
        })

        return result_payload

    except Exception as exc:
        logger.exception("Celery task failed for task_id=%s", task_id)
        bus.publish(task_id, EventType.ERROR, {
            "message": f"Pipeline error: {exc}",
            "code": "PIPELINE_ERROR",
            "traceback": traceback.format_exc()[-2000:],
        })
        return {"success": False, "error": str(exc)}
