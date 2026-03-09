# Offline AI-Powered Code Debugger using RAG and Multi-Agent Architecture

Local-first AI debugging platform for Python projects.  
The stack is designed to run fully on your machine:

- FastAPI backend for execution, analysis, and fix generation
- Local GGUF model via `llama-cpp-python`
- React/Vite frontend
- Optional desktop wrapper using `pywebview`

## Architecture

- `app.py`: API orchestration layer (routing, middleware, pipeline coordination).
- `backend/config.py`: Centralized runtime config/env parsing and bootstrap validation.
- `backend/caching.py`: Shared TTL caches + fixed-window rate limiter primitives.
- `backend/schemas.py`: Strict Pydantic API contracts.
- `src/agents.py`: Multi-agent logic (analysis, fix generation, verification, complexity, security).
- `src/rag_engine.py`: JSON-based local knowledge lookup.
- `src/Scanner.py`: Workspace scanning and context extraction.
- `frontend/`: React UI for debugging sessions and patch workflows.
- `knowledge_base/`: Local troubleshooting data.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for runtime diagram and layer details.

## Requirements

- Python 3.10+ recommended
- Node.js 18+ and npm
- Optional: local GGUF model at `models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`

Install dependencies:

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Frontend API endpoint can be overridden via `frontend/.env`:

```bash
cp frontend/.env.example frontend/.env
```

Download model (optional but required for AI fix generation):

```bash
python download_model.py
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `OFFLINE_DEBUGGER_WORKSPACE_ROOT` | project root | Restricts debug/apply operations to this root |
| `OFFLINE_DEBUGGER_UPLOAD_DIR` | `<workspace>/uploads` | Upload storage directory |
| `OFFLINE_DEBUGGER_ALLOWED_ORIGINS` | localhost origins | CORS allow-list (comma separated) |
| `OFFLINE_DEBUGGER_MAX_UPLOAD_BYTES` | `2097152` | Upload limit |
| `OFFLINE_DEBUGGER_MAX_SNIPPET_CHARS` | `200000` | Snippet/fix payload cap |
| `OFFLINE_DEBUGGER_EXEC_TIMEOUT_SECONDS` | `10` | Timeout for executed target scripts |
| `OFFLINE_DEBUGGER_CACHE_TTL_SECONDS` | `300` | Debug response cache TTL |
| `OFFLINE_DEBUGGER_CACHE_MAX_ENTRIES` | `256` | Cache capacity |
| `OFFLINE_DEBUGGER_SCAN_CACHE_TTL_SECONDS` | `5` | Workspace scan cache TTL |
| `OFFLINE_DEBUGGER_ANALYSIS_CACHE_TTL_SECONDS` | `120` | Complexity/security analysis cache TTL |
| `OFFLINE_DEBUGGER_WORKSPACE_INSIGHTS_TTL_SECONDS` | `30` | Workspace analytics cache TTL |
| `OFFLINE_DEBUGGER_WORKSPACE_INSIGHTS_MAX_FILES` | `120` | Max files sampled for workspace analytics |
| `OFFLINE_DEBUGGER_RATE_LIMIT_PER_MINUTE` | `120` | Per-client API rate limit window |
| `OFFLINE_DEBUGGER_MAX_PIPELINES` | `4` | Max concurrent debug pipelines |
| `OFFLINE_DEBUGGER_FAST_MODE_DEFAULT` | `0` | Default pipeline mode (`1` = fast) |
| `OFFLINE_DEBUGGER_ENABLE_SECURITY_AUDIT` | `1` | Enables heavy security audit phase |
| `OFFLINE_DEBUGGER_DISABLE_MODEL` | `0` | Set `1` to skip model loading |
| `OFFLINE_DEBUGGER_MODEL_PATH` | Qwen GGUF path | Override model path |
| `OFFLINE_DEBUGGER_HOST` | `0.0.0.0` | API bind host |
| `OFFLINE_DEBUGGER_PORT` | `8000` | API bind port |
| `OFFLINE_DEBUGGER_LOG_LEVEL` | `INFO` | Backend logging level |

## Run

Web mode (backend + frontend):

```bash
python run_app.py
```

`run_app.py` now auto-selects free ports if defaults are occupied.
Optional explicit ports:

```bash
python run_app.py <backend_port> <frontend_port>
```

UI includes `Fast` and `Full` pipeline modes:

- `Fast`: lower latency single-pass fix generation.
- `Full`: full orchestration + security audit.
- `Insights` tab: cached workspace analytics (hotspots, grades, largest files).
- `Validate Patch`: pre-commit safety gate for syntax/security/complexity drift.

Desktop mode:

```bash
python desktop_app.py
```

Backend health endpoint:

```text
GET http://localhost:8000/health
```

Additional product endpoints:

```text
POST http://localhost:8000/debug_batch
GET  http://localhost:8000/workspace_insights
GET  http://localhost:8000/metrics
POST http://localhost:8000/validate_fix
```

`/workspace_insights` now supports `ETag` for conditional GETs.
`/scan_project` supports `query`, `offset`, and `limit` for server-side filtering/pagination.

## Testing

```bash
python -m pytest
```

For CI-friendly backend setup without heavy LLM compilation:

```bash
pip install -r requirements-test.txt
python -m pytest
```

Run full local release preflight:

```bash
python scripts/preflight.py
```

## CI

GitHub Actions workflow is included at `.github/workflows/ci.yml` and runs:

- Python compile + backend tests (LLM disabled)
- Frontend lint + production build

## Docker

Build and run:

```bash
docker compose up --build
```

The default container runs with `OFFLINE_DEBUGGER_DISABLE_MODEL=1`.
To enable local model runtime in container builds, set build arg `INSTALL_LLM=1`.

Deployment recommendations and hardening checklist:
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## Desktop Release

Package a Windows desktop binary with PyInstaller:

```bash
pip install pyinstaller
python scripts/build_desktop.py
```

Output:

```text
dist/OfflineDebugger/
```

## Security Posture

- File operations are restricted to workspace root.
- Uploads are extension/size validated.
- Request models reject unexpected fields.
- Auto-fix writes to `fixed_<filename>.py` to avoid destructive overwrite.
- CORS defaults to explicit localhost origins.
- Request tracing headers (`X-Request-ID`, timing) and secure response headers are added.
- In-memory per-client rate limiting is enforced on heavy API endpoints.
