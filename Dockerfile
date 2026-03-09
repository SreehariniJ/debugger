FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

ARG INSTALL_LLM=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OFFLINE_DEBUGGER_DISABLE_MODEL=1 \
    OFFLINE_DEBUGGER_HOST=0.0.0.0 \
    OFFLINE_DEBUGGER_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-test.txt ./requirements-test.txt
RUN pip install --no-cache-dir -r requirements-test.txt
RUN if [ "$INSTALL_LLM" = "1" ]; then pip install --no-cache-dir "llama-cpp-python>=0.2.90" "huggingface_hub>=0.23.0"; fi

COPY . .
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
