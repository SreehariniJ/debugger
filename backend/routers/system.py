import time
from fastapi import APIRouter
from backend.config import (
    PROCESS_START_TIME, FAST_MODE_DEFAULT, ENABLE_SECURITY_AUDIT,
    SCAN_CACHE_TTL_SECONDS, WORKSPACE_INSIGHTS_TTL_SECONDS,
    WORKSPACE_INSIGHTS_MAX_FILES, RATE_LIMIT_PER_MINUTE,
    PIPELINE_CONCURRENCY, LOG_LEVEL, THREAD_POOL_WORKERS,
    get_workspace_root,
    PROJECT_ROOT
)
from backend.dependencies import agents, debug_cache, analysis_cache, workspace_insights_cache, rate_limiter, pipeline_semaphore

router = APIRouter(tags=["system"])

@router.get("/health")
def health_check():
    uptime_seconds = round(time.time() - PROCESS_START_TIME, 2)
    # Note: frontend check is kept in main app or handled here if PROJECT_ROOT is available
    return {
        "status": "online",
        "model_loaded": agents.llm is not None,
        "model_path": agents.model_path,
        "workspace_root": str(get_workspace_root()),
        "uptime_seconds": int(uptime_seconds),
        "frontend_ready": (PROJECT_ROOT / "frontend" / "dist").exists(),
        "fast_mode_default": FAST_MODE_DEFAULT,
        "security_audit_enabled": ENABLE_SECURITY_AUDIT,
        "scan_cache_ttl_seconds": SCAN_CACHE_TTL_SECONDS,
        "workspace_insights_ttl_seconds": WORKSPACE_INSIGHTS_TTL_SECONDS,
        "workspace_insights_max_files": WORKSPACE_INSIGHTS_MAX_FILES,
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "max_pipeline_concurrency": PIPELINE_CONCURRENCY,
        "log_level": LOG_LEVEL,
        "engine": "Offline Debugger Pipeline v10.0.0",
    }

@router.get("/metrics")
def metrics():
    return {
        "uptime_seconds": round(time.time() - PROCESS_START_TIME, 2),
        "thread_pool_workers": THREAD_POOL_WORKERS,
        "max_pipeline_concurrency": PIPELINE_CONCURRENCY,
        "available_pipeline_slots": pipeline_semaphore._value,
        "cache": {
            "debug": debug_cache.stats(),
            "analysis": analysis_cache.stats(),
            "workspace_insights": workspace_insights_cache.stats(),
        },
        "rate_limiter": rate_limiter.stats(),
    }
