from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def _resolve_command(executable: str) -> str | None:
    if os.name == "nt" and executable == "npm":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which(executable)


def run_step(name: str, command: list[str], cwd: Path | None = None, required: bool = True) -> bool:
    print(f"[preflight] {name}: {' '.join(command)}")
    command_exec = _resolve_command(command[0])
    if command_exec:
        command = [command_exec, *command[1:]]
    result = subprocess.run(command, cwd=str(cwd or PROJECT_ROOT), check=False)
    if result.returncode == 0:
        print(f"[preflight] {name}: OK")
        return True
    print(f"[preflight] {name}: FAILED ({result.returncode})")
    if required:
        return False
    print(f"[preflight] {name}: continuing (optional step)")
    return True


def api_smoke() -> bool:
    script = (
        "import os\n"
        "os.environ['OFFLINE_DEBUGGER_DISABLE_MODEL']='1'\n"
        "from fastapi.testclient import TestClient\n"
        "import app\n"
        "client=TestClient(app.app)\n"
        "r=client.get('/health')\n"
        "assert r.status_code==200\n"
        "assert r.json().get('status')=='online'\n"
        "assert r.headers.get('x-request-id')\n"
        "print('api_smoke_ok')\n"
    )
    return run_step("api-smoke", [sys.executable, "-c", script], required=True)


def main() -> int:
    checks: list[bool] = []
    checks.append(run_step("compile", [sys.executable, "-m", "compileall", "app.py", "src", "run_app.py", "desktop_app.py", "tests"]))

    if _resolve_command("npm") and FRONTEND_DIR.exists():
        checks.append(run_step("frontend-lint", ["npm", "run", "lint"], cwd=FRONTEND_DIR))
        checks.append(run_step("frontend-build", ["npm", "run", "build"], cwd=FRONTEND_DIR))
    else:
        print("[preflight] npm not found, skipping frontend checks")

    checks.append(api_smoke())

    try:
        import pytest  # noqa: F401

        checks.append(run_step("pytest", [sys.executable, "-m", "pytest"], required=True))
    except ImportError:
        print("[preflight] pytest not installed, skipping tests")

    ok = all(checks)
    print("[preflight] summary:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
