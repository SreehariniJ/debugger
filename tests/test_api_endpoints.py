from __future__ import annotations

import io
import os
import shutil
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


os.environ["OFFLINE_DEBUGGER_DISABLE_MODEL"] = "1"

import app  # noqa: E402


_raw_client = TestClient(app.app)


def _get_auth_token() -> str:
    response = _raw_client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, f"Auth setup failed: {response.text}"
    return response.json()["access_token"]


_auth_token = _get_auth_token()


class AuthenticatedClient:
    """Wraps TestClient to auto-inject Bearer token."""

    def __init__(self, test_client: TestClient, token: str):
        self._client = test_client
        self._headers = {"Authorization": f"Bearer {token}"}

    def get(self, url, **kwargs):
        headers = {**self._headers, **(kwargs.pop("headers", {}) or {})}
        return self._client.get(url, headers=headers, **kwargs)

    def post(self, url, **kwargs):
        headers = {**self._headers, **(kwargs.pop("headers", {}) or {})}
        return self._client.post(url, headers=headers, **kwargs)


client = AuthenticatedClient(_raw_client, _auth_token)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "online"
    assert "workspace_root" in payload
    assert "uptime_seconds" in payload
    assert "frontend_ready" in payload
    assert "x-request-id" in response.headers
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"


def test_rate_limit_enforced() -> None:
    original_limit = app.rate_limiter.limit_per_minute
    try:
        app.rate_limiter.limit_per_minute = 1
        app.rate_limiter._counter.clear()
        app.rate_limiter._current_window = int(time.time() // 60)

        first = client.get("/scan_project")
        second = client.get("/scan_project")

        assert first.status_code == 200
        assert second.status_code == 429
        assert "request_id" in second.json()
        assert second.headers.get("x-content-type-options") == "nosniff"
    finally:
        app.rate_limiter.limit_per_minute = original_limit
        app.rate_limiter._counter.clear()
        app.rate_limiter._current_window = int(time.time() // 60)


def test_debug_rejects_paths_outside_workspace() -> None:
    response = client.post("/debug", json={"file_path": "..\\..\\Windows\\System32\\drivers\\etc\\hosts"})
    assert response.status_code == 403


def test_debug_snippet_fast_mode_flagged() -> None:
    response = client.post(
        "/debug_snippet",
        json={"code": "num=1\ndenom=0\nprint(num/denom)\n", "mode": "fast"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_mode"] == "fast"
    assert payload["metrics"]["fast_mode"] == 1.0


def test_debug_batch_processes_multiple_files() -> None:
    workspace = Path(app.WORKSPACE_ROOT)
    clean_file = workspace / "_pytest_batch_clean.py"
    buggy_file = workspace / "_pytest_batch_bug.py"

    clean_file.write_text("print('ok')\n", encoding="utf-8")
    buggy_file.write_text("num = 1\ndenom = 0\nprint(num / denom)\n", encoding="utf-8")
    try:
        response = client.post(
            "/debug_batch",
            json={
                "file_paths": [str(clean_file), str(buggy_file)],
                "mode": "fast",
                "max_concurrency": 2,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["requested"] == 2
        assert payload["processed"] == 2
        assert len(payload["items"]) == 2
        assert payload["succeeded"] >= 1
        assert payload["mode"] == "fast"
    finally:
        clean_file.unlink(missing_ok=True)
        buggy_file.unlink(missing_ok=True)


def test_workspace_insights_endpoint_shape() -> None:
    response = client.get("/workspace_insights")
    assert response.status_code == 200
    payload = response.json()
    assert "total_files" in payload
    assert "total_loc" in payload
    assert "grade_distribution" in payload
    assert "hotspots" in payload
    assert "largest_files" in payload
    assert isinstance(payload["grade_distribution"], dict)


def test_workspace_browse_returns_native_selected_path(monkeypatch) -> None:
    previous_picker = app.app.on_open_folder_picker
    app.app.on_open_folder_picker = None
    target_dir = Path(app.WORKSPACE_ROOT) / "_pytest_browse_pick"
    target_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(app, "_open_native_folder_picker", lambda title, initial_path=None: str(target_dir))
    try:
        response = client.post("/workspace/browse")
        assert response.status_code == 200
        assert response.json()["path"] == str(target_dir.resolve())
    finally:
        app.app.on_open_folder_picker = previous_picker
        target_dir.rmdir()


def test_scan_project_query_and_pagination() -> None:
    response = client.get("/scan_project", params={"query": "test_logic", "limit": 1, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["returned"] <= 1
    assert payload["count"] >= payload["returned"]
    assert payload["query"] == "test_logic"


def test_workspace_insights_etag_support() -> None:
    first = client.get("/workspace_insights")
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag

    second = client.get("/workspace_insights", headers={"If-None-Match": etag})
    assert second.status_code == 304


def test_metrics_endpoint_shape() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert "cache" in payload
    assert "rate_limiter" in payload
    assert "max_pipeline_concurrency" in payload
    assert payload["max_pipeline_concurrency"] >= 1
    assert "available_pipeline_slots" in payload


def test_validate_fix_flags_syntax_regression() -> None:
    response = client.post(
        "/validate_fix",
        json={
            "original": "value = 1\nprint(value)\n",
            "fixed": "value = 1\nprint(\n",
            "include_security": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready_to_apply"] is False
    assert payload["syntax"]["fixed_valid"] is False
    assert payload["quality_score"] < 50


def test_validate_fix_accepts_small_safe_patch() -> None:
    response = client.post(
        "/validate_fix",
        json={
            "original": "num = 1\ndenom = 0\nprint(num / denom)\n",
            "fixed": "num = 1\ndenom = 0\nif denom != 0:\n    print(num / denom)\nelse:\n    print(0)\n",
            "include_security": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready_to_apply"] is True
    assert payload["syntax"]["fixed_valid"] is True
    assert payload["quality_score"] >= 70


def test_upload_rejects_non_python_extension() -> None:
    response = client.post(
        "/upload",
        files={"file": ("payload.txt", b"print('x')", "text/plain")},
    )
    assert response.status_code == 400
    assert "Only .py uploads are supported." in response.text


def test_workspace_upload_rejects_non_zip_extension() -> None:
    response = client.post(
        "/workspace/upload",
        files={"file": ("project.txt", b"not-a-zip", "text/plain")},
    )
    assert response.status_code == 400
    assert "Only .zip project archives are supported." in response.text


def test_workspace_upload_accepts_folder_tree() -> None:
    previous_root = Path(app.WORKSPACE_ROOT)
    uploaded_root: Path | None = None
    try:
        response = client.post(
            "/workspace/upload",
            files=[
                ("files", ("main.py", b"print('hello')\n", "text/x-python")),
                ("relative_paths", (None, "sample_project/main.py")),
                ("files", ("helper.py", b"def run():\n    return 1\n", "text/x-python")),
                ("relative_paths", (None, "sample_project/pkg/helper.py")),
                ("files", ("notes.txt", b"demo\n", "text/plain")),
                ("relative_paths", (None, "sample_project/notes.txt")),
            ],
        )
        assert response.status_code == 200
        payload = response.json()
        uploaded_root = Path(payload["path"])

        assert uploaded_root.exists()
        assert uploaded_root != previous_root
        assert payload["python_files"] == 2
        assert payload["extracted_files"] == 3
        assert (uploaded_root / "main.py").exists()
        assert (uploaded_root / "pkg" / "helper.py").exists()

        scanned = client.get("/scan_project")
        assert scanned.status_code == 200
        listed_paths = [item["rel_path"] for item in scanned.json().get("files", [])]
        assert "main.py" in listed_paths
        assert "pkg\\helper.py" in listed_paths or "pkg/helper.py" in listed_paths
    finally:
        restore = client.post("/workspace/root", json={"path": str(previous_root)})
        assert restore.status_code == 200
        if uploaded_root and uploaded_root.exists():
            shutil.rmtree(uploaded_root, ignore_errors=True)


def test_workspace_upload_sets_root_and_extracts_archive() -> None:
    previous_root = Path(app.WORKSPACE_ROOT)
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("sample_project/main.py", "print('hello')\n")
        bundle.writestr("sample_project/README.md", "demo\n")

    uploaded_root: Path | None = None
    try:
        response = client.post(
            "/workspace/upload",
            files={
                "file": (
                    "sample_project.zip",
                    archive_bytes.getvalue(),
                    "application/zip",
                )
            },
        )
        assert response.status_code == 200
        payload = response.json()
        uploaded_root = Path(payload["path"])

        assert uploaded_root.exists()
        assert uploaded_root != previous_root
        assert payload["python_files"] == 1
        assert payload["extracted_files"] >= 2
        assert (uploaded_root / "sample_project" / "main.py").exists()

        scanned = client.get("/scan_project")
        assert scanned.status_code == 200
        listed_names = [item["name"] for item in scanned.json().get("files", [])]
        assert "main.py" in listed_names
    finally:
        restore = client.post("/workspace/root", json={"path": str(previous_root)})
        assert restore.status_code == 200
        if uploaded_root and uploaded_root.exists():
            shutil.rmtree(uploaded_root, ignore_errors=True)


def test_apply_fix_overwrites_original_file() -> None:
    workspace = Path(app.WORKSPACE_ROOT)
    target = workspace / "_pytest_sample.py"

    target.write_text("value = 1\nprint(value)\n", encoding="utf-8")
    try:
        response = client.post(
            "/apply_fix",
            json={
                "file_path": str(target),
                "fixed_code": "```python\nvalue = 2\nprint(value)\n```",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert Path(payload["path"]).exists()
        assert target.exists()
        assert "value = 2" in target.read_text(encoding="utf-8")
    finally:
        target.unlink(missing_ok=True)


def test_apply_fix_rejects_directory_path() -> None:
    workspace = Path(app.WORKSPACE_ROOT)
    target_dir = workspace / "_pytest_dir_target.py"

    target_dir.mkdir(exist_ok=True)
    try:
        response = client.post(
            "/apply_fix",
            json={
                "file_path": str(target_dir),
                "fixed_code": "value = 2\nprint(value)\n",
            },
        )
        assert response.status_code == 400
        assert "Expected a file path" in response.text
    finally:
        target_dir.rmdir()
