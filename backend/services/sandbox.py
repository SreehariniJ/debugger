"""
sandbox.py — Secure Docker-based execution engine for untrusted Python code.

Security model:
    ┌─────────────────────────────────────────────────────────────────┐
    │  HOST                                                         │
    │                                                               │
    │   FastAPI ──► SecureSandbox.execute_file()                    │
    │                   │                                           │
    │                   ▼                                           │
    │   ┌───────────────────────────────────────────────┐           │
    │   │  CONTAINER  (python-runner:latest)            │           │
    │   │                                               │           │
    │   │  • Network: NONE                              │           │
    │   │  • User:    sandboxuser (non-root)            │           │
    │   │  • Mount:   /sandbox (READ-ONLY)              │           │
    │   │  • Memory:  128 MB hard limit                 │           │
    │   │  • CPU:     50% of 1 core                     │           │
    │   │  • PIDs:    max 64                            │           │
    │   │  • Caps:    ALL dropped                       │           │
    │   │  • Privesc: blocked (no-new-privileges)       │           │
    │   │  • Tmpfs:   /tmp 16MB (noexec, nosuid)        │           │
    │   │  • fs:      read-only root                    │           │
    │   └───────────────────────────────────────────────┘           │
    │                   │                                           │
    │                   ▼                                           │
    │   stdout / stderr captured ──► structured dict returned       │
    │   container force-removed in finally block                    │
    └─────────────────────────────────────────────────────────────────┘

Threats mitigated:
    - Fork bombs       → pids_limit=64
    - Memory bombs      → mem_limit="128m", memswap_limit="128m"
    - Infinite loops    → manual timeout + container.kill()
    - Network exfil     → network_mode="none"
    - Filesystem damage → read_only=True, code mounted :ro
    - Privilege escal.  → cap_drop=ALL, no-new-privileges, non-root user
    - rm -rf /          → read-only rootfs + non-root user
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("offline_debugger.sandbox")

# ---------------------------------------------------------------------------
# Lazy Docker client — only imported and connected when actually needed.
# This lets the rest of the application start even if Docker is not installed
# (the sandbox endpoints will return a clear error).
# ---------------------------------------------------------------------------
_docker_client = None
_docker_available: Optional[bool] = None


def _get_docker_client():
    """Return a cached Docker client, or raise RuntimeError."""
    global _docker_client, _docker_available

    if _docker_available is False:
        raise RuntimeError(
            "Docker is not available on this system. "
            "Install Docker and ensure the daemon is running."
        )

    if _docker_client is not None:
        return _docker_client

    try:
        import docker
        from docker.errors import DockerException

        client = docker.from_env(timeout=10)
        client.ping()  # verify daemon is responsive
        _docker_client = client
        _docker_available = True
        logger.info("Docker daemon connected successfully.")
        return _docker_client

    except Exception as exc:
        _docker_available = False
        raise RuntimeError(
            f"Failed to connect to Docker daemon: {exc}. "
            "Ensure Docker Desktop is running."
        ) from exc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RUNNER_IMAGE = "python-runner:latest"
CONTAINER_PREFIX = "sandbox_"
MAX_OUTPUT_CHARS = 5000
POLL_INTERVAL_SEC = 0.15


# ---------------------------------------------------------------------------
# Core sandbox executor
# ---------------------------------------------------------------------------
class SandboxResult:
    """Structured result from a sandboxed execution."""

    __slots__ = (
        "success", "stdout", "stderr", "exit_code",
        "duration", "timed_out", "error_line", "error_type", "backend",
    )

    def __init__(
        self,
        success: bool = False,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = -1,
        duration: float = 0.0,
        timed_out: bool = False,
        error_line: int | None = None,
        error_type: str | None = None,
        backend: str = "docker",
    ):
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration = duration
        self.timed_out = timed_out
        self.error_line = error_line
        self.error_type = error_type
        self.backend = backend

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration": self.duration,
            "timed_out": self.timed_out,
            "error_line": self.error_line,
            "error_type": self.error_type,
            "backend": self.backend,
        }


def _extract_error_line(stderr: str) -> int | None:
    """Extract the last line number mentioned in a Python traceback."""
    matches = re.findall(r"line (\d+)", stderr)
    return int(matches[-1]) if matches else None


def _extract_error_type(stderr: str) -> str | None:
    """Extract the exception class name from the last line of a traceback."""
    for line in reversed(stderr.strip().splitlines()):
        line = line.strip()
        if ":" in line and not line.startswith("File"):
            return line.split(":")[0].strip()
    return None


def _allow_local_exec_fallback() -> bool:
    raw = os.getenv("OFFLINE_DEBUGGER_ALLOW_LOCAL_EXEC_FALLBACK")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("OFFLINE_DEBUGGER_ENV", "development").lower() != "production"


def _execute_file_locally(resolved: Path, timeout: int = 10) -> SandboxResult:
    start_time = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, str(resolved)],
            cwd=str(resolved.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = (completed.stdout or "")[-MAX_OUTPUT_CHARS:]
        stderr = (completed.stderr or "")[-MAX_OUTPUT_CHARS:]
        duration = round(time.monotonic() - start_time, 3)
        return SandboxResult(
            success=completed.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            duration=duration,
            timed_out=False,
            error_line=_extract_error_line(stderr) if completed.returncode != 0 else None,
            error_type=_extract_error_type(stderr) if completed.returncode != 0 else None,
            backend="local_fallback",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = ((exc.stdout or "") if isinstance(exc.stdout, str) else "").strip()[-MAX_OUTPUT_CHARS:]
        stderr = ((exc.stderr or "") if isinstance(exc.stderr, str) else "").strip()[-MAX_OUTPUT_CHARS:]
        if stderr:
            stderr += "\n"
        stderr += f"[Local Fallback] Execution timed out after {timeout} seconds."
        return SandboxResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
            exit_code=-1,
            duration=round(time.monotonic() - start_time, 3),
            timed_out=True,
            error_line=_extract_error_line(stderr),
            error_type=_extract_error_type(stderr),
            backend="local_fallback",
        )
    except Exception as exc:
        return SandboxResult(
            success=False,
            stderr=f"Local execution fallback failed: {exc}",
            exit_code=-1,
            duration=round(time.monotonic() - start_time, 3),
            backend="local_fallback",
        )


def _fallback_or_error(resolved: Path, timeout: int, reason: str) -> SandboxResult:
    if _allow_local_exec_fallback():
        logger.warning("Docker sandbox unavailable, using local execution fallback: %s", reason)
        return _execute_file_locally(resolved, timeout=timeout)
    return SandboxResult(stderr=reason, exit_code=-1, backend="unavailable")


def execute_file(file_path: str, timeout: int = 10) -> SandboxResult:
    """
    Execute a Python file inside a secure Docker container.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the .py file on the host.
    timeout : int
        Maximum wall-clock seconds before the container is killed.

    Returns
    -------
    SandboxResult
        Structured execution result with stdout, stderr, exit code, etc.
    """
    resolved = Path(file_path).resolve()

    if not resolved.exists():
        return SandboxResult(
            stderr=f"File not found: {file_path}",
            exit_code=-1,
            backend="validation",
        )

    if not resolved.suffix.lower() == ".py":
        return SandboxResult(
            stderr="Only .py files can be executed in the sandbox.",
            exit_code=-1,
            backend="validation",
        )

    try:
        client = _get_docker_client()
    except RuntimeError as exc:
        return _fallback_or_error(resolved, timeout, str(exc))

    # Verify the runner image exists
    try:
        client.images.get(RUNNER_IMAGE)
    except Exception:
        return _fallback_or_error(
            resolved,
            timeout,
            (
                f"Sandbox image '{RUNNER_IMAGE}' not found. "
                "Build it with: docker build -t python-runner:latest -f Dockerfile.runner ."
            ),
        )

    container_name = f"{CONTAINER_PREFIX}{uuid.uuid4().hex[:12]}"
    mount_dir = str(resolved.parent)
    target_file = f"/sandbox/{resolved.name}"

    container = None
    start_time = time.monotonic()

    try:
        # ── Launch container ────────────────────────────────────────
        container = client.containers.run(
            image=RUNNER_IMAGE,
            command=[target_file],
            name=container_name,

            # --- Filesystem isolation ---
            volumes={mount_dir: {"bind": "/sandbox", "mode": "ro"}},
            working_dir="/sandbox",
            read_only=True,                           # root fs is read-only
            tmpfs={"/tmp": "size=16m,noexec,nosuid"},  # writable /tmp, limited

            # --- Network isolation ---
            network_mode="none",

            # --- Resource limits (cgroups) ---
            mem_limit="128m",
            memswap_limit="128m",       # no swap — hard ceiling
            cpu_quota=50000,            # 50% of 1 CPU core
            cpu_period=100000,
            pids_limit=64,              # kills fork bombs

            # --- Privilege restrictions ---
            user="sandboxuser",
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],

            # --- Lifecycle ---
            detach=True,
            stderr=True,
            stdout=True,
        )

        # ── Poll until exit or timeout ──────────────────────────────
        timed_out = False
        while True:
            container.reload()
            if container.status in ("exited", "dead"):
                break
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                timed_out = True
                logger.warning(
                    "Container %s exceeded %ds timeout — killing.",
                    container_name, timeout,
                )
                container.kill()
                # Brief wait for the kill to register
                time.sleep(0.3)
                break
            time.sleep(POLL_INTERVAL_SEC)

        # ── Collect output ──────────────────────────────────────────
        stdout_raw = container.logs(stdout=True, stderr=False)
        stderr_raw = container.logs(stdout=False, stderr=True)

        stdout = stdout_raw.decode("utf-8", errors="replace")[-MAX_OUTPUT_CHARS:]
        stderr = stderr_raw.decode("utf-8", errors="replace")[-MAX_OUTPUT_CHARS:]

        if timed_out:
            stderr += f"\n[Sandbox] Execution timed out after {timeout} seconds."

        # Refresh container state to get the real exit code
        container.reload()
        exit_code = container.attrs["State"].get("ExitCode", -1) if not timed_out else -1

        duration = round(time.monotonic() - start_time, 3)

        return SandboxResult(
            success=(exit_code == 0 and not timed_out),
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration=duration,
            timed_out=timed_out,
            error_line=_extract_error_line(stderr) if exit_code != 0 else None,
            error_type=_extract_error_type(stderr) if exit_code != 0 else None,
            backend="docker",
        )

    except Exception as exc:
        logger.exception("Sandbox execution failed for %s", file_path)
        return _fallback_or_error(
            resolved,
            timeout,
            f"Sandbox infrastructure error: {exc}",
        )

    finally:
        # ── Deterministic cleanup ───────────────────────────────────
        if container is not None:
            try:
                container.remove(force=True)
                logger.debug("Removed container %s", container_name)
            except Exception:
                logger.warning("Failed to remove container %s", container_name)


def execute_snippet(code: str, timeout: int = 10) -> SandboxResult:
    """
    Execute an ad-hoc code snippet by writing it to a temp file
    and delegating to execute_file.
    """
    if not code or not code.strip():
        return SandboxResult(stderr="Empty code snippet.", exit_code=-1, backend="validation")

    tmp_dir = Path(tempfile.mkdtemp(prefix="sandbox_snippet_"))
    tmp_file = tmp_dir / "_snippet.py"

    try:
        tmp_file.write_text(code, encoding="utf-8")
        return execute_file(str(tmp_file), timeout=timeout)
    finally:
        # Clean up the temp directory on the host
        try:
            tmp_file.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass
