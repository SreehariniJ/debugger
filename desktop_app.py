from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn

from main import app

try:
    import webview
except ImportError:  # pragma: no cover - runtime dependency
    webview = None


BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = int(os.getenv("OFFLINE_DEBUGGER_PORT", "8000"))
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
HEALTH_URL = f"{BACKEND_URL}/health"
PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_INDEX = PROJECT_ROOT / "frontend" / "dist" / "index.html"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "desktop.log"


def _configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


logger = logging.getLogger("desktop_app")


if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def run_backend() -> None:
    logger.info("starting backend host=%s port=%s", BACKEND_HOST, BACKEND_PORT)
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT, log_level="error")


def wait_for_backend(timeout_seconds: int = 30) -> tuple[bool, dict]:
    logger.info("waiting for backend url=%s timeout=%ss", HEALTH_URL, timeout_seconds)
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
                if response.status != 200:
                    time.sleep(0.5)
                    continue

                payload = json.loads(response.read().decode("utf-8", errors="replace"))
                if payload.get("status") == "online":
                    return True, payload
        except Exception:
            time.sleep(0.5)
    return False, {}


def _preflight_checks() -> None:
    if webview is None:
        raise RuntimeError("pywebview is not installed. Run: pip install pywebview")
    if not FRONTEND_INDEX.exists():
        raise RuntimeError(
            "Frontend build artifacts are missing. Run: cd frontend && npm install && npm run build"
        )


def main() -> None:
    _configure_logging()
    logger.info("desktop app boot start")
    _preflight_checks()

    backend_thread = threading.Thread(target=run_backend, daemon=True, name="FastAPI-Backend")
    backend_thread.start()

    ok, health = wait_for_backend()
    if not ok:
        logger.error("backend did not become healthy in time")
        print("Backend failed to initialize within timeout. Check if port 8000 is in use.")
        sys.exit(1)

    logger.info(
        "backend ready model_loaded=%s frontend_ready=%s",
        health.get("model_loaded"),
        health.get("frontend_ready"),
    )

    logger.info("launching desktop window")
    try:
        window = webview.create_window(
            "Offline AI-Powered Code Debugger using RAG and Multi-Agent Architecture",
            BACKEND_URL,
            width=1300,
            height=900,
            min_size=(900, 700),
            background_color="#09090b",
        )

        # Integration: Backend calls this to open a native folder dialog
        # Removed thread-unsafe handle_browse_request to fallback to app.py PowerShell picker
        app.on_open_folder_picker = None

        webview.start(debug=False)
    except Exception as exc:
        logger.exception("desktop window failed: %s", exc)
        print(f"Desktop UI failed: {exc}")
        print(f"Fallback: open {BACKEND_URL} in your browser.")
    finally:
        logger.info("desktop app closed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("shutdown requested by keyboard interrupt")
