from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173


def _resolve_npm_executable() -> str | None:
    return shutil.which("npm.cmd") or shutil.which("npm")


def _is_port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _find_available_port(preferred_port: int, host: str = "127.0.0.1", max_attempts: int = 50) -> int:
    if preferred_port <= 0:
        preferred_port = 1

    port = preferred_port
    for _ in range(max_attempts):
        if not _is_port_open(port, host=host):
            return port
        port += 1
    raise RuntimeError(f"Could not find an available port after {max_attempts} attempts from {preferred_port}.")


def _wait_for_http(url: str, timeout_seconds: int = 20) -> bool:
    import urllib.request

    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _ensure_frontend_prereqs() -> None:
    if not FRONTEND_DIR.exists():
        raise RuntimeError(f"Missing frontend directory: {FRONTEND_DIR}")
    if _resolve_npm_executable() is None:
        raise RuntimeError("npm was not found in PATH. Install Node.js and npm first.")


def start_services() -> None:
    print("Starting Offline Debugger services...", flush=True)
    _ensure_frontend_prereqs()

    preferred_backend_port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else DEFAULT_BACKEND_PORT
    preferred_frontend_port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else DEFAULT_FRONTEND_PORT
    backend_port = _find_available_port(preferred_backend_port)
    frontend_seed = preferred_frontend_port if preferred_frontend_port != backend_port else preferred_frontend_port + 1
    frontend_port = _find_available_port(frontend_seed)
    backend_health_url = f"http://127.0.0.1:{backend_port}/health"
    backend_api_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"

    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(backend_port)],
        cwd=str(PROJECT_ROOT),
    )

    if not _wait_for_http(backend_health_url):
        backend_proc.terminate()
        raise RuntimeError("Backend failed to become healthy within timeout.")

    frontend_env = dict(**os.environ, VITE_API_URL=backend_api_url)
    npm_executable = _resolve_npm_executable()
    if not npm_executable:
        frontend_proc = None
        backend_proc.terminate()
        raise RuntimeError("npm was not found in PATH. Install Node.js and npm first.")
    frontend_proc = subprocess.Popen(
        [npm_executable, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
        cwd=str(FRONTEND_DIR),
        shell=False,
        env=frontend_env,
    )

    if not _wait_for_http(frontend_url):
        frontend_proc.terminate()
        backend_proc.terminate()
        raise RuntimeError("Frontend failed to become healthy within timeout.")

    print("=" * 56, flush=True)
    print("Offline Debugger is running", flush=True)
    print(f"Frontend: {frontend_url}", flush=True)
    print(f"Backend:  {backend_api_url}", flush=True)
    print("Press Ctrl+C to stop both processes", flush=True)
    print("=" * 56, flush=True)

    try:
        while True:
            if backend_proc.poll() is not None:
                raise RuntimeError("Backend process exited unexpectedly.")
            if frontend_proc.poll() is not None:
                raise RuntimeError("Frontend process exited unexpectedly.")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...", flush=True)
    finally:
        for proc in (frontend_proc, backend_proc):
            if proc.poll() is None:
                proc.terminate()
        for proc in (frontend_proc, backend_proc):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("Shutdown complete.", flush=True)


if __name__ == "__main__":
    start_services()
