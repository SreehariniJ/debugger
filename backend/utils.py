import os
import sys
import uuid
import time
import shutil
import zipfile
import io
import subprocess
import hashlib
import json
import difflib
from pathlib import Path
from fastapi import HTTPException, UploadFile
from backend.config import MAX_PROJECT_UPLOAD_BYTES, get_workspace_root, logger

def _safe_resolve_workspace_path(
    raw_path: str,
    *,
    must_exist: bool,
    enforce_python: bool = True,
) -> Path:
    workspace_root = get_workspace_root()
    candidate_raw = raw_path.strip()
    if not candidate_raw:
        raise HTTPException(status_code=400, detail="file_path is required.")

    path_obj = Path(candidate_raw)
    candidate = path_obj if path_obj.is_absolute() else workspace_root / path_obj
    resolved = candidate.resolve()

    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Path outside workspace is not allowed.") from exc

    if must_exist and not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    if resolved.exists() and resolved.is_dir():
        raise HTTPException(status_code=400, detail="Expected a file path, got a directory.")

    if enforce_python and resolved.suffix.lower() != ".py":
        raise HTTPException(status_code=400, detail="Only .py files are supported.")

    return resolved

def _safe_upload_name(filename: str | None) -> str:
    safe_name = Path(filename or "").name.strip()
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid upload filename.")
    if not safe_name.lower().endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py uploads are supported.")
    return safe_name

def _safe_project_archive_name(filename: str | None) -> str:
    safe_name = Path(filename or "").name.strip()
    if safe_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid project archive filename.")
    if not safe_name.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip project archives are supported.")
    return safe_name

def _safe_project_relative_path(raw_path: str) -> Path:
    candidate_raw = (raw_path or "").strip().replace("\\", "/")
    if not candidate_raw:
        raise HTTPException(status_code=400, detail="Project upload contains an empty path.")

    relative_path = Path(candidate_raw)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise HTTPException(status_code=400, detail="Project upload contains unsafe paths.")

    clean_parts = [part for part in relative_path.parts if part not in {"", "."}]
    if not clean_parts:
        raise HTTPException(status_code=400, detail="Project upload contains an invalid path.")

    return Path(*clean_parts)

def _project_slug_from_archive(filename: str) -> str:
    stem = Path(filename).stem.strip().lower()
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem).strip("._-")
    return slug or "project"

def _open_native_folder_picker(title: str, initial_path: Path | None = None) -> str | None:
    if sys.platform != "win32":
        return None

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell_exe = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = str(powershell_exe if powershell_exe.exists() else "powershell.exe")
    selected_path = str((initial_path or get_workspace_root()).resolve()).replace("'", "''")
    dialog_title = title.replace("'", "''")

    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$dialog.Description = '{dialog_title}'; "
        f"$dialog.SelectedPath = '{selected_path}'; "
        "$dialog.ShowNewFolderButton = $false; "
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ [Console]::Out.Write($dialog.SelectedPath) }"
    )

    try:
        utf8_script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; " + script
        
        result = subprocess.run(
            [command, "-NoProfile", "-NonInteractive", "-STA", "-Command", utf8_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            logger.error(
                "Native folder picker PowerShell script failed with exit code %s. Stderr: %s",
                result.returncode,
                result.stderr.strip()
            )
            return None
    except subprocess.TimeoutExpired:
        logger.warning("Folder picker dialog timed out after 30 seconds")
        return None
    except Exception as exc:
        logger.error("Native folder picker process failed: %s", exc)
        return None

    picked_path = (result.stdout or "").strip()
    return picked_path or None

def _persist_workspace_root(root_path: Path) -> None:
    from backend.config import WORKSPACE_CONFIG_FILE
    WORKSPACE_CONFIG_FILE.write_text(str(root_path), encoding="utf-8")

def _etag_for_payload(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(encoded).hexdigest()
    return f'W/"{digest}"'

def _generate_unified_diff(original: str, fixed: str) -> str:
    a = original.splitlines(keepends=True)
    b = fixed.splitlines(keepends=True)
    diff = difflib.unified_diff(a, b, fromfile="original", tofile="fixed")
    return "".join(diff)
