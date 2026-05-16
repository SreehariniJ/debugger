import asyncio
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from functools import lru_cache

# Ensure src is in path for backend sub-modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

from rag_engine import LocalRAGEngine
from scanner import CodeScanner
from agents import DebuggingAgents
from backend.caching import TimedResponseCache, TimedValueCache, InMemoryRateLimiter
from backend.config import (
    SCAN_CACHE_TTL_SECONDS, THREAD_POOL_WORKERS,
    CACHE_TTL_SECONDS, CACHE_MAX_ENTRIES, ANALYSIS_CACHE_TTL_SECONDS,
    WORKSPACE_INSIGHTS_TTL_SECONDS, PIPELINE_CONCURRENCY,
    RATE_LIMIT_PER_MINUTE, get_workspace_root, set_workspace_root
)
from backend.auth import decode_access_token, get_user_by_username
from backend.database import get_db
from backend.models import User

def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None

# --- Singletons via Dependency Injection ---

@lru_cache()
def get_scanner() -> CodeScanner:
    return CodeScanner(str(get_workspace_root()), scan_cache_ttl_seconds=SCAN_CACHE_TTL_SECONDS)

@lru_cache()
def get_rag() -> LocalRAGEngine:
    return LocalRAGEngine(data_dir="knowledge_base")

@lru_cache()
def get_agents() -> DebuggingAgents:
    return DebuggingAgents()

@lru_cache()
def _build_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=THREAD_POOL_WORKERS)


def get_executor() -> ThreadPoolExecutor:
    executor = _build_executor()
    if getattr(executor, "_shutdown", False):
        _build_executor.cache_clear()
        executor = _build_executor()
    return executor

@lru_cache()
def get_rate_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(limit_per_minute=RATE_LIMIT_PER_MINUTE)

@lru_cache()
def get_debug_cache() -> TimedResponseCache:
    return TimedResponseCache(ttl_seconds=CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES)

@lru_cache()
def get_analysis_cache() -> TimedValueCache:
    return TimedValueCache(ttl_seconds=ANALYSIS_CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES)

@lru_cache()
def get_workspace_insights_cache() -> TimedValueCache:
    return TimedValueCache(
        ttl_seconds=WORKSPACE_INSIGHTS_TTL_SECONDS,
        max_entries=8,
    )

@lru_cache()
def get_pipeline_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(PIPELINE_CONCURRENCY)

async def run_in_executor(func, *args, executor=None):
    if executor is None:
        executor = get_executor() # Fallback for non-DI calls during transition
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func, *args)

def reinitialize_workspace(new_root_path: Path):
    scanner = get_scanner()
    resolved_root = set_workspace_root(new_root_path)
    insights_cache = get_workspace_insights_cache()
    scanner.project_path = resolved_root
    scanner.invalidate_scan_cache()
    get_debug_cache().clear()
    get_analysis_cache().clear()
    insights_cache.clear()
    return resolved_root

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user

# --- Lazy Transitional Globals (For Unmigrated Routers) ---
# These use __getattr__ pattern to avoid eager model/service loading at import time,
# which speeds up startup and avoids import-time side effects in test contexts.
class _LazyProxy:
    """Defers singleton construction until first attribute access."""
    __slots__ = ("_factory", "_instance")
    def __init__(self, factory):
        object.__setattr__(self, "_factory", factory)
        object.__setattr__(self, "_instance", None)
    def _resolve(self):
        inst = object.__getattribute__(self, "_instance")
        if inst is None:
            inst = object.__getattribute__(self, "_factory")()
            object.__setattr__(self, "_instance", inst)
        return inst
    def __getattr__(self, name):
        return getattr(self._resolve(), name)
    def __call__(self, *args, **kwargs):
        return self._resolve()(*args, **kwargs)

scanner = _LazyProxy(get_scanner)
rag = _LazyProxy(get_rag)
agents = _LazyProxy(get_agents)
executor = _LazyProxy(get_executor)
rate_limiter = _LazyProxy(get_rate_limiter)
debug_cache = _LazyProxy(get_debug_cache)
analysis_cache = _LazyProxy(get_analysis_cache)
workspace_insights_cache = _LazyProxy(get_workspace_insights_cache)
pipeline_semaphore = _LazyProxy(get_pipeline_semaphore)
