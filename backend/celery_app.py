"""
celery_app.py — Celery application instance for distributed task execution.

Start a worker:
    celery -A backend.celery_app worker --loglevel=info --pool=solo

The --pool=solo flag is important on Windows and for LLM workloads
that don't release the GIL. For Linux production, use --pool=prefork
with --concurrency=N.

Architecture:
    ┌──────────┐     dispatch     ┌─────────────┐     broker     ┌────────┐
    │  FastAPI  │ ──────────────► │   Celery     │ ◄───────────► │  Redis  │
    │  (web)   │                  │   Worker     │               │        │
    └──────────┘                  │              │  pub/sub       │        │
         ▲                        │  tasks.py    │ ──────────────►│        │
         │       SSE              │              │               │        │
         └────────────────────────└─────────────┘               └────────┘
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is on the path so the worker can import agents, scanner, etc.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from celery import Celery
from backend.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND, logger

celery_app = Celery(
    "offline_debugger",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_acks_late=True,               # Re-deliver if worker dies mid-task
    worker_prefetch_multiplier=1,       # Don't prefetch (LLM tasks are heavy)

    # Result expiry
    result_expires=600,                 # 10 minutes

    # Concurrency — 1 per worker for LLM-bound tasks
    worker_concurrency=1,

    # Task routes
    task_routes={
        "backend.tasks.run_debug_pipeline": {"queue": "debug"},
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["backend"])

logger.info("Celery app configured: broker=%s", CELERY_BROKER_URL)
