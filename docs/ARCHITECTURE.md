# Offline Debugger Architecture

## Runtime Diagram

```text
+------------------------------+
| React/Vite Frontend          |
| - Debug workflow UI          |
| - Insights + patch review    |
+--------------+---------------+
               | HTTP/JSON
+--------------v---------------+
| FastAPI API Layer            |
| - Validation (Pydantic)      |
| - Security headers + CORS    |
| - Rate limiting middleware   |
+--------------+---------------+
               |
+--------------v---------------+
| Debug Pipeline Core          |
| - Runtime execution capture  |
| - RAG query + analyzer       |
| - Fix generation + critique  |
| - Fix validator              |
+-------+-----------+----------+
        |           |
+-------v-------+ +-v-----------------+
| Local Caches  | | Security/Quality  |
| - Debug cache | | - Complexity scan |
| - Analytics   | | - Security audit  |
| - Insights    | | - Patch gating    |
+---------------+ +-------------------+
        |
+-------v-----------------------------+
| Workspace + Knowledge Base          |
| - Python files                      |
| - upload/fixed_*.py outputs         |
| - local JSON knowledge docs         |
+-------------------------------------+
```

## Layers

- `backend/config.py`: environment parsing, runtime defaults, path bootstrap.
- `backend/caching.py`: reusable TTL caches and in-memory rate limiter.
- `backend/schemas.py`: API contracts for requests/responses.
- `app.py`: API orchestration, middleware, endpoints, pipeline execution.
- `src/agents.py`, `src/Scanner.py`, `src/rag_engine.py`: AI and static analysis services.

## Performance Controls

- LRU-like TTL caches for debug responses, code analytics, and workspace insights.
- Bounded thread pool for blocking analyzer/model tasks.
- Concurrency guard for pipeline execution via `OFFLINE_DEBUGGER_MAX_PIPELINES`.
- `ETag` support for `/workspace_insights` to reduce repeated payload transfers.

