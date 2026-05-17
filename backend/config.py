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


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(value, minimum)
    return value


def _resolve_runtime_path(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    return candidate.resolve()


import sys
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys._MEIPASS)
    APP_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    APP_ROOT = PROJECT_ROOT

WORKSPACE_CONFIG_FILE = APP_ROOT / ".workspace_root"

def _get_initial_workspace() -> Path:
    # 1. Check environment variable
    env_root = os.getenv("OFFLINE_DEBUGGER_WORKSPACE_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        if candidate.exists():
            return candidate
    
    # 2. Check persistent config file
    if WORKSPACE_CONFIG_FILE.exists():
        try:
            saved_path = WORKSPACE_CONFIG_FILE.read_text(encoding="utf-8").strip()
            if saved_path:
                candidate = Path(saved_path).resolve()
                if candidate.exists():
                    return candidate
        except Exception:
            pass
            
    # 3. Default to project root
    return PROJECT_ROOT

WORKSPACE_ROOT = _get_initial_workspace()
UPLOAD_DIR = Path(os.getenv("OFFLINE_DEBUGGER_UPLOAD_DIR", str(PROJECT_ROOT / "uploads"))).resolve()
UPLOADED_PROJECTS_ROOT = Path(
    os.getenv("OFFLINE_DEBUGGER_UPLOADED_PROJECTS_DIR", str(PROJECT_ROOT / "_uploaded_projects"))
).resolve()
MODEL_1_5B_PATH = str(_resolve_runtime_path(
    os.getenv("OFFLINE_DEBUGGER_MODEL_1_5B_PATH", "models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf")
))
MODEL_7B_PATH = str(_resolve_runtime_path(
    os.getenv("OFFLINE_DEBUGGER_MODEL_7B_PATH", "models/qwen2.5-coder-7b-instruct-q4_k_m.gguf")
))
# Legacy path for graceful fallback if needed
MODEL_PATH = MODEL_1_5B_PATH
MODEL_CONTEXT_TOKENS = _env_int("OFFLINE_DEBUGGER_MODEL_CONTEXT_TOKENS", 4096, minimum=1024)
MODEL_BATCH_SIZE = _env_int("OFFLINE_DEBUGGER_MODEL_BATCH_SIZE", 256, minimum=32)
MODEL_THREADS = _env_int("OFFLINE_DEBUGGER_MODEL_THREADS", min(os.cpu_count() or 4, 8), minimum=1)
MODEL_MAX_OUTPUT_TOKENS = _env_int("OFFLINE_DEBUGGER_MODEL_MAX_OUTPUT_TOKENS", 1024, minimum=128)
MODEL_ANALYSIS_MAX_TOKENS = _env_int("OFFLINE_DEBUGGER_MODEL_ANALYSIS_MAX_TOKENS", 320, minimum=64)
MODEL_RETRY_ATTEMPTS = _env_int("OFFLINE_DEBUGGER_MODEL_RETRY_ATTEMPTS", 2, minimum=1)
MODEL_TEMPERATURE = _env_float("OFFLINE_DEBUGGER_MODEL_TEMPERATURE", 0.05, minimum=0.0)
MODEL_RETRY_TEMPERATURE = _env_float("OFFLINE_DEBUGGER_MODEL_RETRY_TEMPERATURE", 0.2, minimum=0.0)
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
SANDBOX_MAX_PAYLOAD = _env_int("OFFLINE_DEBUGGER_SANDBOX_MAX_PAYLOAD", 1_048_576, minimum=1000)
SANDBOX_MAX_OUTPUT = _env_int("OFFLINE_DEBUGGER_SANDBOX_MAX_OUTPUT", 5000, minimum=500)
EVENTBUS_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_EVENTBUS_TTL_SECONDS", 300, minimum=10)
EVENTBUS_MAX_EVENTS = _env_int("OFFLINE_DEBUGGER_EVENTBUS_MAX_EVENTS", 200, minimum=10)
CACHE_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_CACHE_TTL_SECONDS", 300, minimum=10)
CACHE_MAX_ENTRIES = _env_int("OFFLINE_DEBUGGER_CACHE_MAX_ENTRIES", 512, minimum=16)
SCAN_CACHE_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_SCAN_CACHE_TTL_SECONDS", 5, minimum=0)
ANALYSIS_CACHE_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_ANALYSIS_CACHE_TTL_SECONDS", 300, minimum=5)
WORKSPACE_INSIGHTS_TTL_SECONDS = _env_int("OFFLINE_DEBUGGER_WORKSPACE_INSIGHTS_TTL_SECONDS", 30, minimum=5)
WORKSPACE_INSIGHTS_MAX_FILES = _env_int("OFFLINE_DEBUGGER_WORKSPACE_INSIGHTS_MAX_FILES", 120, minimum=10)
ALLOWED_ORIGINS = _env_csv(
    "OFFLINE_DEBUGGER_ALLOWED_ORIGINS",
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    ],
)

# In dev mode, we allow dynamic ports on localhost to support run_app.py Vite servers.
# In prod mode, this relies strictly on ALLOWED_ORIGINS.
ENVIRONMENT = os.getenv("OFFLINE_DEBUGGER_ENV", "development").lower()
CORS_ORIGIN_REGEX = os.getenv(
    "OFFLINE_DEBUGGER_CORS_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if ENVIRONMENT == "development" else None
)

HOST = os.getenv("OFFLINE_DEBUGGER_HOST", "0.0.0.0")
PORT = _env_int("OFFLINE_DEBUGGER_PORT", 8001, minimum=1)
LOG_LEVEL = os.getenv("OFFLINE_DEBUGGER_LOG_LEVEL", "INFO").upper()
RATE_LIMIT_PER_MINUTE = _env_int("OFFLINE_DEBUGGER_RATE_LIMIT_PER_MINUTE", 120, minimum=10)
FAST_MODE_DEFAULT = _env_bool("OFFLINE_DEBUGGER_FAST_MODE_DEFAULT", default=False)
ENABLE_SECURITY_AUDIT = _env_bool("OFFLINE_DEBUGGER_ENABLE_SECURITY_AUDIT", default=True)
PROCESS_START_TIME = time.time()

DATABASE_URL = os.getenv("OFFLINE_DEBUGGER_DATABASE_URL", "sqlite:///./offline_debugger.db")
TEST_DATABASE_URL = os.getenv("OFFLINE_DEBUGGER_TEST_DATABASE_URL", "sqlite:///./test.db")

# ── Redis & Celery ──────────────────────────────────────────────────────────
REDIS_URL = os.getenv("OFFLINE_DEBUGGER_REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("OFFLINE_DEBUGGER_CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("OFFLINE_DEBUGGER_CELERY_RESULT_BACKEND", REDIS_URL)
USE_DISTRIBUTED = _env_bool("OFFLINE_DEBUGGER_USE_DISTRIBUTED", default=False)


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("offline_debugger")


def get_workspace_root() -> Path:
    return WORKSPACE_ROOT


def set_workspace_root(root_path: Path | str) -> Path:
    global WORKSPACE_ROOT
    WORKSPACE_ROOT = Path(root_path).resolve()
    return WORKSPACE_ROOT


def ensure_runtime_paths() -> None:
    workspace_root = get_workspace_root()
    if workspace_root != PROJECT_ROOT and not workspace_root.exists():
        logger.warning(
            "Configured workspace does not exist; falling back to project root: %s",
            workspace_root,
        )
        set_workspace_root(PROJECT_ROOT)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADED_PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
