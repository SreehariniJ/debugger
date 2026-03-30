import os
import sys
import time
import uuid
import shutil
import zipfile
import io
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from backend.config import (
    MAX_PROJECT_UPLOAD_BYTES,
    WORKSPACE_INSIGHTS_MAX_FILES,
    WORKSPACE_INSIGHTS_TTL_SECONDS,
    UPLOADED_PROJECTS_ROOT,
    get_workspace_root as get_active_workspace_root,
    logger,
)
from backend.dependencies import (
    scanner, agents, workspace_insights_cache, reinitialize_workspace, 
    run_in_executor
)
from backend.utils import (
    _safe_resolve_workspace_path, _safe_project_archive_name, 
    _safe_project_relative_path, _project_slug_from_archive,
    _open_native_folder_picker, _persist_workspace_root,
    _etag_for_payload
)

router = APIRouter(tags=["workspace"])

def _read_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _loc_count(code_text: str) -> int:
    return sum(1 for line in code_text.splitlines() if line.strip())

def _compute_workspace_insights() -> dict[str, Any]:
    cache_key = "workspace"
    cached = workspace_insights_cache.get(cache_key)
    if cached is not None:
        return cached

    files = scanner.scan_workspace()
    total_files = len(files)
    total_size_bytes = sum(int(item.get("size", 0) or 0) for item in files)

    inspected_files: list[dict[str, Any]] = []
    total_loc = 0
    grade_distribution: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    
    # Batch file reading and complexity analysis for speed
    file_data: list[tuple[dict[str, Any], str]] = []
    for file_info in files[:WORKSPACE_INSIGHTS_MAX_FILES]:
        file_path = file_info.get("path")
        if not isinstance(file_path, str):
            continue
        try:
            code_text = _read_file_text(Path(file_path))
            file_data.append((file_info, code_text))
        except OSError:
            continue

    for file_info, code_text in file_data:
        complexity = agents.complexity_agent(code_text)
        loc = int(complexity.get("loc") or _loc_count(code_text))
        grade = str(complexity.get("grade") or "F")
        if grade not in grade_distribution:
            grade = "F"
        grade_distribution[grade] += 1
        total_loc += loc

        inspected_files.append(
            {
                "name": file_info.get("name"),
                "rel_path": file_info.get("rel_path"),
                "size": int(file_info.get("size", 0) or 0),
                "loc": loc,
                "complexity_score": int(complexity.get("complexity_score") or 0),
                "grade": grade,
                "mtime": float(file_info.get("mtime", 0.0) or 0.0),
            }
        )

    average_size_kb = round((total_size_bytes / total_files) / 1024, 2) if total_files else 0.0
    avg_loc_per_file = round(total_loc / len(inspected_files), 2) if inspected_files else 0.0

    largest_files = sorted(inspected_files, key=lambda item: item["size"], reverse=True)[:5]
    hotspots = sorted(
        inspected_files,
        key=lambda item: (item["complexity_score"], item["loc"]),
        reverse=True,
    )[:5]
    recent_files = sorted(inspected_files, key=lambda item: item["mtime"], reverse=True)[:5]

    payload = {
        "generated_at": time.time(),
        "total_files": total_files,
        "total_size_bytes": total_size_bytes,
        "average_size_kb": average_size_kb,
        "inspected_files": len(inspected_files),
        "analysis_sample_limit": WORKSPACE_INSIGHTS_MAX_FILES,
        "total_loc": total_loc,
        "avg_loc_per_file": avg_loc_per_file,
        "grade_distribution": grade_distribution,
        "largest_files": largest_files,
        "hotspots": hotspots,
        "recent_files": recent_files,
        "cache_ttl_seconds": WORKSPACE_INSIGHTS_TTL_SECONDS,
    }
    workspace_insights_cache.set(cache_key, payload)
    return payload

@router.get("/scan_project")
async def scan_project(
    query: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
):
    files = scanner.scan_workspace()
    query_value = query.strip().lower()
    if query_value:
        files = [
            item
            for item in files
            if query_value in str(item.get("name", "")).lower()
            or query_value in str(item.get("rel_path", "")).lower()
        ]

    total = len(files)
    paged_files = files[offset : offset + limit]
    return {
        "files": paged_files,
        "count": total,
        "returned": len(paged_files),
        "offset": offset,
        "limit": limit,
        "query": query,
    }

@router.get("/workspace/root")
async def get_workspace_root():
    return {"path": str(get_active_workspace_root())}

@router.post("/workspace/root")
async def set_workspace_root(request: dict[str, str]):
    new_path_str = request.get("path")
    if not new_path_str:
        raise HTTPException(status_code=400, detail="Path is required.")
    
    new_path = Path(new_path_str).resolve()
    if not new_path.exists():
        raise HTTPException(status_code=404, detail="Path does not exist.")
    if not new_path.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory.")
    
    reinitialize_workspace(new_path)
    _persist_workspace_root(new_path)

    logger.info(f"Workspace root updated to: {new_path}")
    return {"message": "Workspace root updated.", "path": str(new_path)}

@router.get("/workspace_insights")
async def workspace_insights(request: Request):
    payload = await run_in_executor(_compute_workspace_insights)
    etag = _etag_for_payload(payload)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(content=payload, headers={"ETag": etag})

# Native folder picker logic
@router.post("/workspace/browse")
async def browse_workspace_root():
    try:
        if sys.platform == "win32":
            selected_path = await run_in_executor(
                _open_native_folder_picker,
                "Select Project Workspace Folder",
                get_active_workspace_root(),
            )
            if selected_path:
                return {"path": str(Path(selected_path).resolve())}
            raise HTTPException(status_code=400, detail="User cancelled or dialog unavailable")
        raise HTTPException(status_code=400, detail="Native picker only available on Windows.")
    except Exception as exc:
        if isinstance(exc, HTTPException): raise exc
        raise HTTPException(status_code=500, detail=str(exc))

def _extract_workspace_archive(payload: bytes, archive_name: str) -> tuple[Path, int, int]:
    from backend.config import MAX_PROJECT_UPLOAD_BYTES
    projects_root = UPLOADED_PROJECTS_ROOT
    projects_root.mkdir(parents=True, exist_ok=True)

    project_slug = _project_slug_from_archive(archive_name)
    destination = (projects_root / f"{project_slug}_{int(time.time())}_{uuid.uuid4().hex[:8]}").resolve()
    destination.mkdir(parents=True, exist_ok=False)

    extracted_files = 0
    python_files = 0
    total_uncompressed = 0
    max_uncompressed_bytes = max(10 * 1024 * 1024, MAX_PROJECT_UPLOAD_BYTES * 25)

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            for member in members:
                if member.is_dir(): continue
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts: continue
                
                clean_parts = [part for part in member_path.parts if part not in {"", "."}]
                if not clean_parts: continue

                output_path = (destination / Path(*clean_parts)).resolve()
                total_uncompressed += max(member.file_size, 0)
                if total_uncompressed > max_uncompressed_bytes:
                    raise HTTPException(status_code=413, detail="Archive expands beyond allowed size.")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as src, output_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                extracted_files += 1
                if output_path.suffix.lower() == ".py": python_files += 1
    except Exception as exc:
        shutil.rmtree(destination, ignore_errors=True)
        if isinstance(exc, HTTPException): raise
        raise HTTPException(status_code=500, detail=f"Failed to extract archive: {exc}")

    return destination, extracted_files, python_files

async def _store_uploaded_workspace_folder(files: list[UploadFile], relative_paths: list[str]) -> tuple[Path, int, int]:
    from backend.config import MAX_PROJECT_UPLOAD_BYTES
    normalized_files = []
    total_size = 0
    for idx, uploaded in enumerate(files):
        provided_path = relative_paths[idx] if idx < len(relative_paths) else (uploaded.filename or "")
        rel_path = _safe_project_relative_path(provided_path)
        payload = await uploaded.read(MAX_PROJECT_UPLOAD_BYTES + 1)
        total_size += len(payload)
        if total_size > MAX_PROJECT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Project upload too large.")
        normalized_files.append((rel_path, payload))

    project_name = normalized_files[0][0].parts[0]
    projects_root = UPLOADED_PROJECTS_ROOT
    projects_root.mkdir(parents=True, exist_ok=True)
    destination = (projects_root / f"{_project_slug_from_archive(project_name)}_{int(time.time())}_{uuid.uuid4().hex[:8]}").resolve()
    destination.mkdir(parents=True, exist_ok=False)

    written = 0
    py_files = 0
    
    # Identify and strip common project-slug prefix to land files in destination root
    if normalized_files and len(normalized_files[0][0].parts) > 1:
        to_strip = normalized_files[0][0].parts[0]
    else:
        to_strip = None

    for rel_path, payload in normalized_files:
        if to_strip and len(rel_path.parts) > 1 and rel_path.parts[0] == to_strip:
            effective_path = Path(*rel_path.parts[1:])
        else:
            effective_path = rel_path
            
        output_path = (destination / effective_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
        written += 1
        if output_path.suffix.lower() == ".py": py_files += 1
    
    return destination.resolve(), written, py_files

@router.post("/workspace/upload")
async def upload_workspace_project(
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
    relative_paths: list[str] = Form(default=[]),
):
    from backend.config import MAX_PROJECT_UPLOAD_BYTES
    uploaded_files = [item for item in (files or []) if item is not None]

    if uploaded_files:
        project_root, extracted, python_files = await _store_uploaded_workspace_folder(uploaded_files, relative_paths)
    elif file is not None:
        safe_name = _safe_project_archive_name(file.filename)
        payload = await file.read(MAX_PROJECT_UPLOAD_BYTES + 1)
        if len(payload) > MAX_PROJECT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Project upload too large.")
        project_root, extracted, python_files = _extract_workspace_archive(payload, safe_name)
    else:
        raise HTTPException(status_code=400, detail="Select a project folder or ZIP archive.")

    reinitialize_workspace(project_root)
    _persist_workspace_root(project_root)

    return {
        "message": "Project uploaded and root updated.",
        "path": str(project_root),
        "extracted_files": extracted,
        "python_files": python_files,
    }
