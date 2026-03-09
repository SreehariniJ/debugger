# Deployment Strategy

## Recommended Environments

1. Development: `python run_app.py` + Vite dev server.
2. Staging: Docker Compose with model disabled, production frontend build.
3. Production: containerized FastAPI + pre-built static assets, reverse proxy (Nginx/Caddy), health/metrics scraping.

## Container Pattern

1. Build frontend assets in a Node stage.
2. Build backend runtime in Python slim image.
3. Install `requirements-test.txt` by default, optionally enable LLM dependencies with `INSTALL_LLM=1`.
4. Run `uvicorn app:app --host 0.0.0.0 --port 8000`.

## Runtime Hardening Checklist

- Set strict `OFFLINE_DEBUGGER_ALLOWED_ORIGINS`.
- Pin `OFFLINE_DEBUGGER_WORKSPACE_ROOT` to the intended workspace mount.
- Tune `OFFLINE_DEBUGGER_RATE_LIMIT_PER_MINUTE`.
- Tune `OFFLINE_DEBUGGER_MAX_PIPELINES` to CPU/RAM budget.
- Monitor `/health` and `/metrics`.
- Keep `OFFLINE_DEBUGGER_DISABLE_MODEL=1` for environments without local model runtime.

## Scale-Out Notes

- This service uses in-memory rate limiting and caches; horizontal scaling requires sticky sessions or external shared stores.
- For multi-instance production, move rate-limit and cache data to Redis and keep workspace mounts isolated per tenant/workspace.

