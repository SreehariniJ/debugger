import time
import uuid
import sys
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

# Setup paths for modules
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from backend.config import HOST, PORT, ALLOWED_ORIGINS, CORS_ORIGIN_REGEX, PROJECT_ROOT, WORKSPACE_ROOT, logger, ensure_runtime_paths
from backend.routers import (
    auth, debug, system, workspace, runtime, stream, patch,
    sessions, teams, comments, profiling, visualization
)
from backend.dependencies import get_executor, get_rate_limiter
from backend.auth import decode_access_token
from backend.database import init_db, SessionLocal
from backend.auth import bootstrap_auth_data

ensure_runtime_paths()

async def _eventbus_gc():
    from backend.services.event_bus import get_event_bus
    import logging
    while True:
        try:
            await asyncio.sleep(60)
            await get_event_bus().cleanup_expired()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger("offline_debugger.event_bus_gc").error("GC error: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        bootstrap_auth_data(db)
    finally:
        db.close()
    logger.info("Startup workspace_root=%s", WORKSPACE_ROOT)
    
    # Start EventBus Garbage Collector
    gc_task = asyncio.create_task(_eventbus_gc())
    
    yield
    
    gc_task.cancel()
    try:
        await gc_task
    except asyncio.CancelledError:
        pass
        
    get_executor().shutdown(wait=False, cancel_futures=True)

app = FastAPI(
    title="Offline AI-Powered Code Debugger",
    version="6.1.0",
    description="Refactored modular ASGI entrypoint.",
    lifespan=lifespan,
)

# Exception handlers
from fastapi.exceptions import HTTPException
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

app.add_middleware(GZipMiddleware, minimum_size=1024)

# Filter out empty kwargs to allow proper default overrides 
cors_kwargs = {
    "allow_origins": ALLOWED_ORIGINS,
    "allow_credentials": False,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if CORS_ORIGIN_REGEX:
    cors_kwargs["allow_origin_regex"] = CORS_ORIGIN_REGEX

RATE_LIMITED_PREFIXES = {
    "/debug", "/debug_snippet", "/debug_batch", "/upload",
    "/workspace/upload", "/apply_fix", "/validate_fix",
    "/analyze_complexity", "/scan_project", "/workspace_insights", "/diff",
    "/patch/",
}
AUTH_EXEMPT_PREFIXES = ("/health", "/auth/", "/assets/", "/vite.svg", "/stream/", "/task/")

def _is_rate_limited_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in RATE_LIMITED_PREFIXES)

def _is_auth_exempt(path: str) -> bool:
    if path == "/" or path.endswith(".html") or path.endswith(".js") or path.endswith(".css"):
        return True
    return any(path.startswith(prefix) for prefix in AUTH_EXEMPT_PREFIXES)

def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None

def _apply_common_response_headers(response, request_id: str, elapsed_ms: float, path: str):
    if hasattr(response, "headers"):
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if (path.startswith("/debug") or path.startswith("/upload") or 
            path.startswith("/workspace/upload") or path.startswith("/apply_fix")):
            response.headers["Cache-Control"] = "no-store"

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    path = request.url.path

    rate_limiter = get_rate_limiter()
    if _is_rate_limited_path(path):
        client_host = request.client.host if request.client and request.client.host else "unknown"
        if not rate_limiter.allow(client_host):
            elapsed_ms = (time.perf_counter() - started) * 1000
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please retry later.", "request_id": request_id},
            )
            _apply_common_response_headers(response, request_id, elapsed_ms, path)
            return response

    if request.method != "OPTIONS" and not _is_auth_exempt(path):
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
        request_id, request.method, path, response.status_code, elapsed_ms,
    )
    return response

# CORS must be the OUTERMOST middleware to handle preflights and add headers 
# to error responses generated by inner middlewares (auth, etc.)
app.add_middleware(CORSMiddleware, **cors_kwargs)

app.include_router(auth.router)
app.include_router(debug.router)
app.include_router(system.router)
app.include_router(workspace.router)
app.include_router(runtime.router)
app.include_router(stream.router)
app.include_router(patch.router)
app.include_router(sessions.router)
app.include_router(teams.router)
app.include_router(comments.router)
app.include_router(profiling.router)
app.include_router(visualization.router)

frontend_path = PROJECT_ROOT / "frontend" / "dist"
if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/{rest_of_path:path}", include_in_schema=False)
    async def serve_frontend(rest_of_path: str):
        return FileResponse(str(frontend_path / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
