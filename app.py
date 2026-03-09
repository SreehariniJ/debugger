import asyncio
import difflib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from agents import DebuggingAgents
from backend.caching import InMemoryRateLimiter, TimedResponseCache, TimedValueCache
# --- App Infrastructure ---

from backend.config import (
    ALLOWED_ORIGINS,
    ANALYSIS_CACHE_TTL_SECONDS,
    CACHE_MAX_ENTRIES,
    CACHE_TTL_SECONDS,
    ENABLE_SECURITY_AUDIT,
    EXEC_TIMEOUT_SECONDS,
    FAST_MODE_DEFAULT,
    HOST,
    LOG_LEVEL,
    MAX_PROJECT_UPLOAD_BYTES,
    MAX_SNIPPET_CHARS,
    MAX_UPLOAD_BYTES,
    MODEL_PATH,
    PIPELINE_CONCURRENCY,
    PORT,
    PROCESS_START_TIME,
    PROJECT_ROOT,
    RATE_LIMIT_PER_MINUTE,
    SCAN_CACHE_TTL_SECONDS,
    THREAD_POOL_WORKERS,
    UPLOAD_DIR,
    WORKSPACE_INSIGHTS_MAX_FILES,
    WORKSPACE_INSIGHTS_TTL_SECONDS,
    WORKSPACE_ROOT,
    ensure_runtime_paths,
    logger,
)
from backend.auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_user_profile,
    register_user,
)
from backend.schemas import (
    ApplyFixRequest,
    BatchDebugRequest,
    ComplexityRequest,
    DebugRequest,
    DebugResponse,
    DiffRequest,
    LoginRequest,
    RegisterRequest,
    SnippetRequest,
    TokenResponse,
    ValidateFixRequest,
)
from rag_engine import LocalRAGEngine
from Scanner import CodeScanner

ensure_runtime_paths()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "startup workspace_root=%s upload_dir=%s model_path=%s rate_limit_per_minute=%s pipeline_concurrency=%s",
        WORKSPACE_ROOT,
        UPLOAD_DIR,
        MODEL_PATH,
        RATE_LIMIT_PER_MINUTE,
        PIPELINE_CONCURRENCY,
    )
    try:
        yield
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)


app = FastAPI(
    title="Offline AI-Powered Code Debugger using RAG and Multi-Agent Architecture",
    version="6.1.0",
    description="Secure, local-first debugging API with agentic repair pipeline.",
    lifespan=lifespan,
)

# Callback for desktop app to handle native folder picking
app.on_open_folder_picker = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

RATE_LIMITED_PREFIXES = {
    "/debug",
    "/debug_snippet",
    "/debug_batch",
    "/upload",
    "/workspace/upload",
    "/apply_fix",
    "/validate_fix",
    "/analyze_complexity",
    "/scan_project",
    "/workspace_insights",
    "/diff",
}
rate_limiter = InMemoryRateLimiter(limit_per_minute=RATE_LIMIT_PER_MINUTE)


def _is_rate_limited_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in RATE_LIMITED_PREFIXES)


def _apply_common_response_headers(
    response: Response,
    request_id: str,
    elapsed_ms: float,
    path: str,
) -> None:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if (
        path.startswith("/debug")
        or path.startswith("/upload")
        or path.startswith("/workspace/upload")
        or path.startswith("/apply_fix")
    ):
        response.headers["Cache-Control"] = "no-store"


AUTH_EXEMPT_PREFIXES = ("/health", "/auth/", "/assets/", "/vite.svg")


def _is_auth_exempt(path: str) -> bool:
    if path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css"):
        return True
    return any(path.startswith(prefix) for prefix in AUTH_EXEMPT_PREFIXES)


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    path = request.url.path

    if _is_rate_limited_path(path):
        client_host = request.client.host if request.client and request.client.host else "unknown"
        if not rate_limiter.allow(client_host):
            elapsed_ms = (time.perf_counter() - started) * 1000
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please retry later.",
                    "request_id": request_id,
                },
            )
            _apply_common_response_headers(response, request_id, elapsed_ms, path)
            return response

    if not _is_auth_exempt(path):
        token = _extract_bearer_token(request)
        if not token:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response = JSONResponse(
                status_code=401,
                content={"detail": "Authentication required.", "request_id": request_id},
            )
            _apply_common_response_headers(response, request_id, elapsed_ms, path)
            return response
        username = decode_access_token(token)
        if not username:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response = JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token.", "request_id": request_id},
            )
            _apply_common_response_headers(response, request_id, elapsed_ms, path)
            return response
        request.state.username = username

    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000

    _apply_common_response_headers(response, request_id, elapsed_ms, path)

    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        path,
        response.status_code,
        elapsed_ms,
    )
    return response


scanner = CodeScanner(str(WORKSPACE_ROOT), scan_cache_ttl_seconds=SCAN_CACHE_TTL_SECONDS)
rag = LocalRAGEngine(data_dir="knowledge_base")
agents = DebuggingAgents(model_path=MODEL_PATH)
executor = ThreadPoolExecutor(max_workers=THREAD_POOL_WORKERS)
debug_cache = TimedResponseCache(ttl_seconds=CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES)
analysis_cache = TimedValueCache(ttl_seconds=ANALYSIS_CACHE_TTL_SECONDS, max_entries=CACHE_MAX_ENTRIES)
workspace_insights_cache = TimedValueCache(
    ttl_seconds=WORKSPACE_INSIGHTS_TTL_SECONDS,
    max_entries=8,
)
pipeline_semaphore = asyncio.Semaphore(PIPELINE_CONCURRENCY)


def _safe_resolve_workspace_path(
    raw_path: str,
    *,
    must_exist: bool,
    enforce_python: bool = True,
) -> Path:
    candidate_raw = raw_path.strip()
    if not candidate_raw:
        raise HTTPException(status_code=400, detail="file_path is required.")

    path_obj = Path(candidate_raw)
    candidate = path_obj if path_obj.is_absolute() else WORKSPACE_ROOT / path_obj
    resolved = candidate.resolve()

    try:
        resolved.relative_to(WORKSPACE_ROOT)
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


def _workspace_upload_dir(root_path: Path) -> Path:
    configured_upload_dir = os.getenv("OFFLINE_DEBUGGER_UPLOAD_DIR")
    if configured_upload_dir:
        candidate = Path(configured_upload_dir).resolve()
        try:
            candidate.relative_to(root_path)
            return candidate
        except ValueError:
            logger.warning(
                "Configured upload dir %s is outside workspace root %s; using workspace-local uploads folder.",
                candidate,
                root_path,
            )
    return (root_path / "uploads").resolve()


def _open_native_folder_picker(title: str, initial_path: Path | None = None) -> str | None:
    if sys.platform != "win32":
        return None

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell_exe = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    command = str(powershell_exe if powershell_exe.exists() else "powershell.exe")
    selected_path = str((initial_path or WORKSPACE_ROOT).resolve()).replace("'", "''")
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
        # Use a more robust PowerShell script that handles UTF8 output explicitly if possible
        # but the simplest fix for UnicodeEncodeError on Windows is to ensure 'encoding="utf-8"' in subprocess.run
        # and tell PowerShell to use UTF8 for its output stream.
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


def _activate_workspace_root(root_path: Path) -> None:
    global WORKSPACE_ROOT, UPLOAD_DIR, scanner

    WORKSPACE_ROOT = root_path
    UPLOAD_DIR = _workspace_upload_dir(root_path)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    scanner = CodeScanner(str(root_path), scan_cache_ttl_seconds=SCAN_CACHE_TTL_SECONDS)
    _invalidate_workspace_caches()


def _extract_workspace_archive(payload: bytes, archive_name: str) -> tuple[Path, int, int]:
    projects_root = (WORKSPACE_ROOT / "_uploaded_projects").resolve()
    projects_root.mkdir(parents=True, exist_ok=True)

    project_slug = _project_slug_from_archive(archive_name)
    destination = (projects_root / f"{project_slug}_{int(time.time())}_{uuid.uuid4().hex[:8]}").resolve()
    try:
        destination.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Upload destination is outside workspace.") from exc
    destination.mkdir(parents=True, exist_ok=False)

    extracted_files = 0
    python_files = 0
    total_uncompressed = 0
    max_uncompressed_bytes = max(10 * 1024 * 1024, MAX_PROJECT_UPLOAD_BYTES * 25)

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if not members:
                raise HTTPException(status_code=400, detail="Archive is empty.")

            for member in members:
                if member.is_dir():
                    continue

                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise HTTPException(status_code=400, detail="Archive contains unsafe paths.")

                clean_parts = [part for part in member_path.parts if part not in {"", "."}]
                if not clean_parts:
                    continue

                relative_member = Path(*clean_parts)
                output_path = (destination / relative_member).resolve()
                try:
                    output_path.relative_to(destination)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail="Archive contains unsafe paths.") from exc

                total_uncompressed += max(member.file_size, 0)
                if total_uncompressed > max_uncompressed_bytes:
                    raise HTTPException(status_code=413, detail="Archive expands beyond allowed size.")

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as src, output_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                extracted_files += 1
                if output_path.suffix.lower() == ".py":
                    python_files += 1
    except zipfile.BadZipFile as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid ZIP archive.") from exc
    except HTTPException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract archive: {exc}") from exc

    if extracted_files == 0:
        shutil.rmtree(destination, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Archive has no files to import.")

    return destination, extracted_files, python_files


async def _store_uploaded_workspace_folder(
    files: list[UploadFile],
    relative_paths: list[str],
) -> tuple[Path, int, int]:
    if not files:
        raise HTTPException(status_code=400, detail="No project files were uploaded.")
    if relative_paths and len(relative_paths) != len(files):
        raise HTTPException(status_code=400, detail="Uploaded project paths did not match uploaded files.")

    normalized_files: list[tuple[Path, bytes]] = []
    total_uploaded_bytes = 0

    for index, uploaded in enumerate(files):
        provided_path = relative_paths[index] if index < len(relative_paths) else (uploaded.filename or "")
        relative_path = _safe_project_relative_path(provided_path)
        remaining_bytes = MAX_PROJECT_UPLOAD_BYTES - total_uploaded_bytes
        if remaining_bytes < 0:
            raise HTTPException(
                status_code=413,
                detail=f"Project upload too large. Max {MAX_PROJECT_UPLOAD_BYTES} bytes.",
            )

        payload = await uploaded.read(remaining_bytes + 1)
        total_uploaded_bytes += len(payload)
        if total_uploaded_bytes > MAX_PROJECT_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Project upload too large. Max {MAX_PROJECT_UPLOAD_BYTES} bytes.",
            )

        normalized_files.append((relative_path, payload))

    common_root = None
    if normalized_files:
        first_parts = normalized_files[0][0].parts
        if len(first_parts) > 1:
            first_root = first_parts[0]
            if all(len(path.parts) > 1 and path.parts[0] == first_root for path, _ in normalized_files):
                common_root = first_root

    project_name = common_root or normalized_files[0][0].parts[0]
    projects_root = (WORKSPACE_ROOT / "_uploaded_projects").resolve()
    projects_root.mkdir(parents=True, exist_ok=True)

    destination = (projects_root / f"{_project_slug_from_archive(project_name)}_{int(time.time())}_{uuid.uuid4().hex[:8]}").resolve()
    try:
        destination.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Upload destination is outside workspace.") from exc
    destination.mkdir(parents=True, exist_ok=False)

    written_files = 0
    python_files = 0
    seen_paths: set[Path] = set()

    try:
        for relative_path, payload in normalized_files:
            final_relative = relative_path
            if common_root and len(relative_path.parts) > 1 and relative_path.parts[0] == common_root:
                final_relative = Path(*relative_path.parts[1:])

            output_path = (destination / final_relative).resolve()
            try:
                output_path.relative_to(destination)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Project upload contains unsafe paths.") from exc

            if output_path in seen_paths:
                raise HTTPException(status_code=400, detail="Project upload contains duplicate paths.")
            seen_paths.add(output_path)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(payload)
            written_files += 1
            if output_path.suffix.lower() == ".py":
                python_files += 1
    except HTTPException:
        shutil.rmtree(destination, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to store project folder: {exc}") from exc

    if written_files == 0:
        shutil.rmtree(destination, ignore_errors=True)
        raise HTTPException(status_code=400, detail="No project files were uploaded.")

    return destination, written_files, python_files


def _extract_error_line(stderr: str, returncode: int) -> str:
    if not stderr.strip():
        return f"RuntimeError: Script exited with code {returncode}."
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else f"RuntimeError: Script exited with code {returncode}."


def run_target_code(file_path: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            [sys.executable, str(file_path)],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_SECONDS,
            cwd=str(file_path.parent),
        )
        if result.returncode == 0:
            return None
        stderr = result.stderr or result.stdout or ""
        return _extract_error_line(stderr, result.returncode)
    except subprocess.TimeoutExpired:
        return "TimeoutError: Script execution exceeded timeout (possible infinite loop)."
    except Exception as exc:
        return str(exc)


async def run_in_executor(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func, *args)


def _available_pipeline_slots() -> int:
    # asyncio.Semaphore does not expose a public getter for available permits.
    return int(getattr(pipeline_semaphore, "_value", 0))


async def _run_debug_pipeline_limited(file_path: Path, *, mode: str = "full") -> DebugResponse:
    async with pipeline_semaphore:
        return await _run_debug_pipeline(file_path, mode=mode)


async def _run_batch_debug_item(file_path_text: str, *, mode: str) -> dict[str, Any]:
    try:
        file_path = _safe_resolve_workspace_path(file_path_text, must_exist=True, enforce_python=True)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return {"file_path": file_path_text, "ok": False, "error": detail}

    try:
        result = await _run_debug_pipeline_limited(file_path, mode=mode)
        return {"file_path": str(file_path), "ok": True, "result": result.model_dump()}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return {"file_path": str(file_path), "ok": False, "error": detail}
    except Exception as exc:
        logger.exception("Batch debug failed for %s: %s", file_path, exc)
        return {"file_path": str(file_path), "ok": False, "error": "Debug pipeline failed unexpectedly."}


def _read_file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _sanitize_markdown_code(code_text: str) -> str:
    return code_text.replace("```python", "").replace("```", "").strip()


def _syntax_check(code_text: str) -> tuple[bool, str | None]:
    try:
        compile(code_text, "<snippet>", "exec")
        return True, None
    except SyntaxError as exc:
        line_number = exc.lineno or "?"
        return False, f"SyntaxError: {exc.msg} (line {line_number})"


def _loc_count(code_text: str) -> int:
    return sum(1 for line in code_text.splitlines() if line.strip())


def _critical_issue_count(audit_payload: dict[str, Any] | None) -> int:
    if not audit_payload:
        return 0
    issues = audit_payload.get("issues") or []
    return sum(1 for item in issues if str(item.get("risk", "")).upper() == "CRITICAL")


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
    for file_info in files[:WORKSPACE_INSIGHTS_MAX_FILES]:
        file_path = file_info.get("path")
        if not isinstance(file_path, str):
            continue

        try:
            code_text = _read_file_text(Path(file_path))
        except OSError:
            continue

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


def _invalidate_workspace_caches() -> None:
    scanner.invalidate_scan_cache()
    workspace_insights_cache.clear()


def _cache_key(code_text: str, error_msg: str) -> str:
    payload = f"{code_text}\n---\n{error_msg}".encode("utf-8", errors="ignore")
    return hashlib.sha256(payload).hexdigest()


def _etag_for_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(encoded).hexdigest()
    return f'W/"{digest}"'


def _normalize_mode(mode: str | None) -> str:
    if mode and mode.lower() == "fast":
        return "fast"
    if mode and mode.lower() == "full":
        return "full"
    if FAST_MODE_DEFAULT:
        return "fast"
    return "full"


def _code_hash(code_text: str) -> str:
    return hashlib.sha256(code_text.encode("utf-8", errors="ignore")).hexdigest()


async def _get_cached_code_analytics(
    code_text: str,
    *,
    include_security: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not code_text:
        return None, None

    key = f"{_code_hash(code_text)}:sec={1 if include_security else 0}"
    cached = analysis_cache.get(key)
    if cached is not None:
        return cached

    complexity = await run_in_executor(agents.complexity_agent, code_text)
    security = None
    if include_security and ENABLE_SECURITY_AUDIT:
        security = await run_in_executor(agents.security_audit_agent, code_text)

    analysis_cache.set(key, (complexity, security))
    return complexity, security


async def _run_debug_pipeline(file_path: Path, *, mode: str = "full") -> DebugResponse:
    grand_start = time.time()
    path_text = str(file_path)
    pipeline_mode = _normalize_mode(mode)
    fast_mode = pipeline_mode == "fast"
    error_msg = await run_in_executor(run_target_code, file_path)

    code_text = ""
    try:
        code_text = await run_in_executor(_read_file_text, file_path)
    except OSError:
        code_text = ""

    if not error_msg:
        include_security = (not fast_mode) and ENABLE_SECURITY_AUDIT
        complexity_data, security_data = await _get_cached_code_analytics(
            code_text,
            include_security=include_security,
        )
        source_payload = code_text if len(code_text) <= MAX_SNIPPET_CHARS else None
        return DebugResponse(
            success=True,
            error=None,
            complexity=complexity_data,
            security_audit=security_data,
            total_time=round(time.time() - grand_start, 3),
            source_path=path_text,
            source_code=source_payload,
            pipeline_mode=pipeline_mode,
        )

    try:
        key = f"{_cache_key(code_text, error_msg)}:mode={pipeline_mode}"
        cached = debug_cache.get(key)
        if cached:
            result = cached.model_copy(deep=True)
            result.total_time = round(time.time() - grand_start, 3)
            metrics = dict(result.metrics or {})
            metrics["cache_status"] = 1.0
            metrics["fast_mode"] = 1.0 if fast_mode else 0.0
            result.metrics = metrics
            result.source_path = path_text
            if result.source_code is None and len(code_text) <= MAX_SNIPPET_CHARS:
                result.source_code = code_text
            result.pipeline_mode = pipeline_mode
            return result

        # Phase 1: static extraction, KB lookup, severity/complexity/security.
        p1_start = time.time()
        include_security = (not fast_mode) and ENABLE_SECURITY_AUDIT
        code_context, local_knowledge, severity = await asyncio.gather(
            run_in_executor(scanner.get_context_for_file, path_text),
            run_in_executor(rag.query_docs, error_msg),
            run_in_executor(agents.severity_agent, error_msg),
        )
        complexity, security_data = await _get_cached_code_analytics(
            code_text,
            include_security=include_security,
        )
        p1_time = round(time.time() - p1_start, 3)

        if isinstance(code_context, str) and code_context.startswith("Error reading file:"):
            code_context = code_text

        # Phase 2: fix generation (full orchestration or fast single pass).
        p2_start = time.time()
        if agents.llm is None:
            orchestration_result = {
                "success": False,
                "fix": "",
                "reason": "LLM unavailable; install model to generate fixes.",
                "path_taken": "LLM unavailable fallback",
            }
        elif fast_mode:
            quick_fix = await run_in_executor(agents.code_fixer_agent, code_context, error_msg, 1)
            orchestration_result = {
                "success": bool(quick_fix),
                "fix": quick_fix,
                "path_taken": "Fast mode single-pass generation",
            }
        else:
            workspace_files = await run_in_executor(scanner.scan_workspace)
            orchestration_result = await agents.viper_orchestration(error_msg, code_context, workspace_files)
        p2_time = round(time.time() - p2_start, 3)

        # Phase 3: synthesis + confidence.
        p3_start = time.time()
        fixed_code = orchestration_result.get("fix") or None
        analysis_data = await run_in_executor(agents.multi_agent_pipeline, error_msg, code_context, local_knowledge)
        p3_time = round(time.time() - p3_start, 3)

        confidence = agents.confidence_agent(
            error_msg,
            str(analysis_data.get("analysis", "")),
            fixed_code,
        )
        total_time = round(time.time() - grand_start, 3)

        response = DebugResponse(
            success=False,
            error=error_msg,
            analysis=analysis_data.get("analysis"),
            explanation=analysis_data.get("explanation"),
            verification=orchestration_result.get("path_taken"),
            fixed_code=fixed_code,
            severity=severity,
            confidence=confidence,
            complexity=complexity,
            security_audit=security_data,
            metrics={
                "scan_rag": float(p1_time),
                "viper_orchestration": float(p2_time),
                "final_synthesis": float(p3_time),
                "fast_mode": 1.0 if fast_mode else 0.0,
                "security_audit": 1.0 if include_security else 0.0,
            },
            total_time=total_time,
            source_path=path_text,
            source_code=code_text if len(code_text) <= MAX_SNIPPET_CHARS else None,
            pipeline_mode=pipeline_mode,
        )

        debug_cache.set(key, response)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        logger.exception("Debug pipeline failed for file %s: %s", path_text, exc)
        raise HTTPException(status_code=500, detail="Debug pipeline failed unexpectedly.") from exc


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.exception(
        "Unhandled exception request_id=%s method=%s path=%s error=%s",
        request_id,
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = create_access_token(user["username"])
    return TokenResponse(access_token=token, user=user)


@app.post("/auth/register", response_model=TokenResponse)
def register(request: RegisterRequest):
    user = register_user(request.username, request.password, request.display_name)
    if not user:
        raise HTTPException(status_code=409, detail="Username already exists.")
    token = create_access_token(user["username"])
    return TokenResponse(access_token=token, user=user)


@app.get("/auth/me")
def auth_me(request: Request):
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    profile = get_user_profile(username)
    if not profile:
        raise HTTPException(status_code=401, detail="User not found.")
    return profile


@app.get("/health")
def health_check():
    uptime_seconds = round(time.time() - PROCESS_START_TIME, 2)
    frontend_index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    return {
        "status": "online",
        "model_loaded": agents.llm is not None,
        "model_path": agents.model_path,
        "workspace_root": str(WORKSPACE_ROOT),
        "frontend_ready": frontend_index.exists(),
        "uptime_seconds": uptime_seconds,
        "fast_mode_default": FAST_MODE_DEFAULT,
        "security_audit_enabled": ENABLE_SECURITY_AUDIT,
        "scan_cache_ttl_seconds": SCAN_CACHE_TTL_SECONDS,
        "workspace_insights_ttl_seconds": WORKSPACE_INSIGHTS_TTL_SECONDS,
        "workspace_insights_max_files": WORKSPACE_INSIGHTS_MAX_FILES,
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "max_pipeline_concurrency": PIPELINE_CONCURRENCY,
        "log_level": LOG_LEVEL,
        "engine": "Offline Debugger Pipeline v6.1.0",
    }


@app.get("/metrics")
def metrics():
    return {
        "uptime_seconds": round(time.time() - PROCESS_START_TIME, 2),
        "thread_pool_workers": THREAD_POOL_WORKERS,
        "max_pipeline_concurrency": PIPELINE_CONCURRENCY,
        "available_pipeline_slots": _available_pipeline_slots(),
        "cache": {
            "debug": debug_cache.stats(),
            "analysis": analysis_cache.stats(),
            "workspace_insights": workspace_insights_cache.stats(),
        },
        "rate_limiter": rate_limiter.stats(),
    }


@app.post("/debug", response_model=DebugResponse)
async def debug_file(request: DebugRequest):
    file_path = _safe_resolve_workspace_path(request.file_path, must_exist=True, enforce_python=True)
    return await _run_debug_pipeline_limited(file_path, mode=request.mode)


@app.post("/debug_batch")
async def debug_batch(request: BatchDebugRequest):
    started = time.time()
    file_paths = [item.strip() for item in request.file_paths if item and item.strip()]
    if not file_paths:
        raise HTTPException(status_code=400, detail="file_paths must include at least one valid path.")

    bounded_concurrency = max(1, min(request.max_concurrency, PIPELINE_CONCURRENCY))
    batch_semaphore = asyncio.Semaphore(bounded_concurrency)

    async def _worker(path_text: str) -> dict[str, Any]:
        async with batch_semaphore:
            return await _run_batch_debug_item(path_text, mode=request.mode)

    items = await asyncio.gather(*[_worker(path_text) for path_text in file_paths])
    succeeded = sum(1 for item in items if item.get("ok"))
    failed = len(items) - succeeded
    return {
        "requested": len(file_paths),
        "processed": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "mode": request.mode,
        "max_concurrency": bounded_concurrency,
        "duration_seconds": round(time.time() - started, 3),
        "items": items,
    }


@app.post("/debug_snippet", response_model=DebugResponse)
async def debug_snippet(request: SnippetRequest):
    if len(request.code) > MAX_SNIPPET_CHARS:
        raise HTTPException(status_code=413, detail=f"Snippet too large. Max {MAX_SNIPPET_CHARS} characters.")

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        dir=str(UPLOAD_DIR),
        prefix="_snippet_",
        encoding="utf-8",
    ) as tmp:
        tmp.write(request.code)
        tmp_path = Path(tmp.name)

    try:
        return await _run_debug_pipeline_limited(tmp_path, mode=request.mode)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@app.post("/analyze_complexity")
async def analyze_complexity(request: ComplexityRequest):
    return agents.complexity_agent(request.code)


@app.get("/scan_project")
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


@app.get("/workspace/root")
async def get_workspace_root():
    return {"path": str(WORKSPACE_ROOT)}


@app.post("/workspace/root")
async def set_workspace_root(request: dict[str, str]):
    new_path_str = request.get("path")
    if not new_path_str:
        raise HTTPException(status_code=400, detail="Path is required.")
    
    new_path = Path(new_path_str).resolve()
    if not new_path.exists():
        raise HTTPException(status_code=404, detail="Path does not exist.")
    if not new_path.is_dir():
        raise HTTPException(status_code=400, detail="Path must be a directory.")
    
    _activate_workspace_root(new_path)

    try:
        _persist_workspace_root(new_path)
    except Exception as exc:
        logger.error(f"Failed to persist workspace root: {exc}")

    logger.info(f"Workspace root updated to: {new_path}")
    return {"message": "Workspace root updated.", "path": str(new_path)}


@app.post("/workspace/browse")
async def browse_workspace_root():
    logger.info("Attempting to open native folder picker...")
    """Opens a native folder picker and returns the selected path."""
    try:
        # If we have a desktop-app-level callback, use it (prioritized)
        if hasattr(app, "on_open_folder_picker") and app.on_open_folder_picker:
            selected_path = await run_in_executor(
                app.on_open_folder_picker, 
                "Select Project Workspace Folder"
            )
            if selected_path:
                return {"path": str(Path(selected_path).resolve())}
            # If no path was selected (user cancelled or timeout), trigger upload fallback
            raise HTTPException(
                status_code=400, 
                detail="Could not open native folder picker: User cancelled or dialog unavailable"
            )

        # Fallback to internal PowerShell picker for Windows
        if sys.platform == "win32":
            selected_path = await run_in_executor(
                _open_native_folder_picker,
                "Select Project Workspace Folder",
                WORKSPACE_ROOT,
            )
            if selected_path:
                return {"path": str(Path(selected_path).resolve())}
            # If no path was selected (user cancelled or timeout), trigger upload fallback
            raise HTTPException(
                status_code=400, 
                detail="Could not open native folder picker: User cancelled or dialog unavailable"
            )
            
        # Fallback (non-desktop mode, non-windows): cannot open native dialogs in generic browser
        raise HTTPException(
            status_code=400, 
            detail="Native folder picker only available in Desktop App mode or on Windows."
        )
    except Exception as exc:
        logger.error(f"Failed to open folder picker: {exc}")
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=500, detail=f"Could not open native folder picker: {exc}")


@app.post("/workspace/upload")
async def upload_workspace_project(
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] | None = File(default=None),
    relative_paths: list[str] = Form(default=[]),
):
    uploaded_files = [item for item in (files or []) if item is not None]

    if uploaded_files:
        project_root, extracted_files, python_files = await _store_uploaded_workspace_folder(
            uploaded_files,
            relative_paths,
        )
        source_label = "folder"
    elif file is not None:
        safe_name = _safe_project_archive_name(file.filename)
        payload = await file.read(MAX_PROJECT_UPLOAD_BYTES + 1)
        if len(payload) > MAX_PROJECT_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Project archive too large. Max {MAX_PROJECT_UPLOAD_BYTES} bytes.",
            )

        project_root, extracted_files, python_files = _extract_workspace_archive(payload, safe_name)
        source_label = safe_name
    else:
        raise HTTPException(status_code=400, detail="Select a project folder or ZIP archive to upload.")

    _activate_workspace_root(project_root)

    try:
        _persist_workspace_root(project_root)
    except Exception as exc:
        logger.error("Failed to persist workspace root after project upload: %s", exc)

    logger.info(
        "Workspace project uploaded source=%s path=%s files=%s python_files=%s",
        source_label,
        project_root,
        extracted_files,
        python_files,
    )
    return {
        "message": "Project uploaded and workspace root updated.",
        "path": str(project_root),
        "extracted_files": extracted_files,
        "python_files": python_files,
    }


@app.get("/workspace_insights")
async def workspace_insights(request: Request):
    payload = await run_in_executor(_compute_workspace_insights)
    etag = _etag_for_payload(payload)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(content=payload, headers={"ETag": etag})


@app.post("/validate_fix")
async def validate_fix(request: ValidateFixRequest):
    clean_fixed = _sanitize_markdown_code(request.fixed)
    if not clean_fixed:
        raise HTTPException(status_code=400, detail="Fixed code is empty after sanitization.")

    original_code = request.original
    original_valid, original_syntax_error = _syntax_check(original_code)
    fixed_valid, fixed_syntax_error = _syntax_check(clean_fixed)

    original_complexity = await run_in_executor(agents.complexity_agent, original_code)
    fixed_complexity = await run_in_executor(agents.complexity_agent, clean_fixed)
    original_complexity_score = int(original_complexity.get("complexity_score") or 0)
    fixed_complexity_score = int(fixed_complexity.get("complexity_score") or 0)
    complexity_delta = fixed_complexity_score - original_complexity_score
    original_loc = int(original_complexity.get("loc") or _loc_count(original_code))
    fixed_loc = int(fixed_complexity.get("loc") or _loc_count(clean_fixed))

    security_enabled = request.include_security and ENABLE_SECURITY_AUDIT
    original_security = None
    fixed_security = None
    new_critical_issues = 0
    if security_enabled:
        original_security, fixed_security = await asyncio.gather(
            run_in_executor(agents.security_audit_agent, original_code),
            run_in_executor(agents.security_audit_agent, clean_fixed),
        )
        new_critical_issues = max(
            0,
            _critical_issue_count(fixed_security) - _critical_issue_count(original_security),
        )

    issues: list[str] = []
    if not fixed_valid:
        issues.append(fixed_syntax_error or "Fixed code contains syntax errors.")
    if clean_fixed.strip() == original_code.strip():
        issues.append("No code changes detected in proposed fix.")
    if complexity_delta > 8:
        issues.append(f"Complexity score increased by {complexity_delta}; review maintainability impact.")
    if original_loc > 0 and fixed_loc > original_loc * 2:
        issues.append("Fix more than doubled effective LOC; review for unnecessary churn.")
    if new_critical_issues > 0:
        issues.append("Fix introduced additional CRITICAL security findings.")

    quality_score = 100
    if not fixed_valid:
        quality_score -= 60
    if clean_fixed.strip() == original_code.strip():
        quality_score -= 20
    if complexity_delta > 8:
        quality_score -= min(25, complexity_delta)
    if original_loc > 0 and fixed_loc > original_loc * 2:
        quality_score -= 10
    if new_critical_issues > 0:
        quality_score -= 35
    quality_score = max(0, quality_score)

    ready_to_apply = (
        fixed_valid
        and clean_fixed.strip() != original_code.strip()
        and complexity_delta <= 12
        and new_critical_issues == 0
    )

    return {
        "ready_to_apply": fixed_valid and quality_score >= 80,
        "quality_score": quality_score,
        "issues": issues,
        "syntax": {
            "original_valid": original_valid,
            "original_error": original_syntax_error,
            "fixed_valid": fixed_valid,
            "fixed_error": fixed_syntax_error,
        },
        "complexity": {
            "original": original_complexity,
            "fixed": fixed_complexity,
            "delta_score": complexity_delta,
            "delta_loc": fixed_loc - original_loc,
        },
        "security": {
            "enabled": security_enabled,
            "original": original_security,
            "fixed": fixed_security,
            "new_critical_issues": new_critical_issues,
        },
    }


@app.post("/upload", response_model=DebugResponse)
async def upload_file(file: UploadFile = File(...), mode: str = "full"):
    safe_name = _safe_upload_name(file.filename)
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload too large. Max {MAX_UPLOAD_BYTES} bytes.")

    file_path = (UPLOAD_DIR / safe_name).resolve()
    try:
        file_path.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Upload destination is outside workspace.") from exc

    file_path.write_bytes(payload)
    _invalidate_workspace_caches()
    return await _run_debug_pipeline_limited(file_path, mode=mode)


@app.post("/diff")
async def compute_diff(request: DiffRequest):
    orig_lines = request.original.splitlines(keepends=True)
    fixed_lines = request.fixed.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            orig_lines,
            fixed_lines,
            fromfile="original.py",
            tofile="fixed.py",
            lineterm="",
        )
    )
    return {"diff": "".join(diff)}


@app.post("/apply_fix")
async def apply_fix(request: ApplyFixRequest):
    target_path = _safe_resolve_workspace_path(request.file_path, must_exist=True, enforce_python=True)

    clean_code = _sanitize_markdown_code(request.fixed_code)
    if not clean_code:
        raise HTTPException(status_code=400, detail="Fixed code is empty after sanitization.")
    if len(clean_code) > MAX_SNIPPET_CHARS:
        raise HTTPException(status_code=413, detail=f"Fixed code exceeds {MAX_SNIPPET_CHARS} characters.")

    target_path.write_text(clean_code, encoding="utf-8")
    _invalidate_workspace_caches()
    return {"message": f"Fixed file applied to {target_path.name}", "path": str(target_path)}


frontend_path = PROJECT_ROOT / "frontend" / "dist"
if frontend_path.exists():
    assets_path = frontend_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

    @app.get("/{rest_of_path:path}")
    async def serve_frontend(rest_of_path: str):
        return FileResponse(str(frontend_path / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
