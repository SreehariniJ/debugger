from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
DESKTOP_ENTRY = PROJECT_ROOT / "desktop_app.py"


def _npm_command() -> str | None:
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def ensure_frontend_dist() -> None:
    if FRONTEND_DIST.exists():
        return
    npm_exec = _npm_command()
    if npm_exec is None:
        raise RuntimeError("frontend/dist is missing and npm is not available to build it.")
    print("[build_desktop] frontend/dist missing; building frontend...")
    subprocess.run([npm_exec, "ci"], cwd=str(PROJECT_ROOT / "frontend"), check=True)
    subprocess.run([npm_exec, "run", "build"], cwd=str(PROJECT_ROOT / "frontend"), check=True)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("PyInstaller is not installed. Run: pip install pyinstaller") from exc


def build() -> None:
    ensure_pyinstaller()
    ensure_frontend_dist()

    sep = os.pathsep
    add_data = [
        f"{PROJECT_ROOT / 'frontend' / 'dist'}{sep}frontend/dist",
        f"{PROJECT_ROOT / 'knowledge_base'}{sep}knowledge_base",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "OfflineDebugger",
        "--collect-submodules",
        "webview",
    ]
    for item in add_data:
        cmd.extend(["--add-data", item])
    cmd.append(str(DESKTOP_ENTRY))

    print("[build_desktop] running:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)
    print("[build_desktop] complete. Binary is in dist/OfflineDebugger")


if __name__ == "__main__":
    build()
