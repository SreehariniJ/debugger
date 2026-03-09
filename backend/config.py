from __future__ import annotations

import logging
import os
import time
from pathlib import Path


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(value, minimum)


def _env_csv(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_CONFIG_FILE = PROJECT_ROOT / ".workspace_root"

def _get_initial_workspace() -> Path:
    # 1. Check environment variable
    env_root = os.getenv("OFFLINE_DEBUGGER_WORKSPACE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    
    # 2. Check persistent config file
    if WORKSPACE_CONFIG_FILE.exists():
        try:
            saved_path = WORKSPACE_CONFIG_FILE.read_text(encoding="utf-8").strip()
            if saved_path:
                return Path(saved_path).resolve()
        except Exception:
            pass
            
    # 3. Default to project root
    return PROJECT_ROOT

WORKSPACE_ROOT = _get_initial_workspace()
UPLOAD_DIR = Path(os.getenv("OFFLINE_DEBUGGER_UPLOAD_DIR", str(WORKSPACE_ROOT / "uploads"))).resolve()
MODEL_PATH = os.getenv("OFFLINE_DEBUGGER_MODEL_PATH", "models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
EXEC_TIMEOUT_SECONDS = _env_int("OFFLINE_DEBUGGER_EXEC_TIMEOUT_SECONDS", 10, minimum=1)
THREAD_POOL_WORKERS = _env_int("OFFLINE_DEBUGGER_THREAD_POOL_WORKERS", 6, minimum=2)
PIPELINE_CONCURRENCY = _env_int("OFFLINE_DEBUGGER_MAX_PIPELINES", 4, minimum=1)
MAX_UPLOAD_BYTES = _env_int("OFFLINE_DEBUGGER_MAX_UPLOAD_BYTES", 2 * 1024 * 1024, minimum=1024)
MAX_PROJECT_UPLOAD_BYTES = _env_int(
    "OFFLINE_DEBUGGER_MAX_PROJECT_UPLOAD_BYTES",
    50 * 1024 * 1024,
    minimum=1024 * 1024,
)
MAX_SNIPPET_CHARS = _env_int("OFFLINE_DEBUGGER_MAX_SNIPPET_CHARS", 200_000, minimum=1000)
CACHE_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_CACHE_TTL_SECONDS", 300, minimum=10)
CACHE_MAX_ENTRIES = _env_int("OFFLINE_DEBUGGER_CACHE_MAX_ENTRIES", 256, minimum=16)
SCAN_CACHE_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_SCAN_CACHE_TTL_SECONDS", 5, minimum=0)
ANALYSIS_CACHE_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_ANALYSIS_CACHE_TTL_SECONDS", 120, minimum=5)
WORKSPACE_INSIGHTS_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_WORKSPACE_INSIGHTS_TTL_SECONDS", 30, minimum=5)
WORKSPACE_INSIGHTS_MAX_FILES = _env_int("OFFLINE_DEBUGGER_WORKSPACE_INSIGHTS_MAX_FILES", 120, minimum=10)
ALLOWED_ORIGINS = _env_csv(
    "OFFLINE_DEBUGGER_ALLOWED_ORIGINS",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
)
HOST = os.getenv("OFFLINE_DEBUGGER_HOST", "0.0.0.0")
PORT = _env_int("OFFLINE_DEBUGGER_PORT", 8000, minimum=1)
LOG_LEVEL = os.getenv("OFFLINE_DEBUGGER_LOG_LEVEL", "INFO").upper()
RATE_LIMIT_PER_MINUTE = _env_int("OFFLINE_DEBUGGER_RATE_LIMIT_PER_MINUTE", 120, minimum=10)
FAST_MODE_DEFAULT = _env_bool("OFFLINE_DEBUGGER_FAST_MODE_DEFAULT", default=False)
ENABLE_SECURITY_AUDIT = _env_bool("OFFLINE_DEBUGGER_ENABLE_SECURITY_AUDIT", default=True)
PROCESS_START_TIME = time.time()


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("offline_debugger")


def ensure_runtime_paths() -> None:
    if WORKSPACE_ROOT != PROJECT_ROOT and not WORKSPACE_ROOT.exists():
        raise RuntimeError(f"Configured workspace does not exist: {WORKSPACE_ROOT}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
