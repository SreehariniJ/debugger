from __future__ import annotations

import shutil
from pathlib import Path


def test_login_and_auth_me(client) -> None:
    login = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["access_token"]
    assert payload["user"]["username"] == "admin"

    profile = client.get("/auth/me")
    assert profile.status_code == 200
    assert profile.json()["username"] == "admin"


def test_health_and_metrics_endpoints(client) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["status"] == "online"
    assert "workspace_root" in health_payload
    assert health.headers.get("x-content-type-options") == "nosniff"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    metrics_payload = metrics.json()
    assert "cache" in metrics_payload
    assert "rate_limiter" in metrics_payload
    assert metrics_payload["max_pipeline_concurrency"] >= 1


def test_debug_snippet_runtime_failure_returns_real_execution_data(client) -> None:
    response = client.post(
        "/debug_snippet",
        json={"code": "num=1\ndenom=0\nprint(num/denom)\n", "mode": "fast"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error_type"] == "ZeroDivisionError"
    assert "ZeroDivisionError" in payload["stderr"]
    assert payload["exit_code"] != 0
    assert payload["execution_backend"] in {"docker", "local_fallback"}
    assert payload["metrics"]["fast_mode"] == 1.0


def test_debug_snippet_success_captures_stdout(client) -> None:
    response = client.post(
        "/debug_snippet",
        json={"code": "print('ok')\n", "mode": "fast"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["stdout"].strip() == "ok"
    assert payload["exit_code"] == 0
    assert payload["error"] is None


def test_upload_then_debug_round_trip(client) -> None:
    upload = client.post(
        "/upload",
        files={"file": ("smoke.py", b"print(1/0)\n", "text/x-python")},
    )
    assert upload.status_code == 200
    upload_payload = upload.json()
    uploaded_path = Path(upload_payload["path"])

    assert uploaded_path.exists()
    assert client.workspace_root in uploaded_path.parents
    assert uploaded_path.parent.name == ".viper_uploads"

    debug = client.post(
        "/debug",
        json={"file_path": str(uploaded_path), "mode": "fast"},
    )
    assert debug.status_code == 200
    debug_payload = debug.json()
    assert debug_payload["success"] is False
    assert debug_payload["error_type"] == "ZeroDivisionError"
    assert debug_payload["source_path"] == str(uploaded_path)


def test_workspace_insights_supports_etag(client) -> None:
    first = client.get("/workspace_insights")
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag

    second = client.get("/workspace_insights", headers={"If-None-Match": etag})
    assert second.status_code == 304


def test_workspace_root_switch_updates_scan_project(client) -> None:
    alternate_root = client.workspace_root / "alternate_project"
    alternate_root.mkdir()
    (alternate_root / "main.py").write_text("print('hello')\n", encoding="utf-8")

    update = client.post("/workspace/root", json={"path": str(alternate_root)})
    assert update.status_code == 200
    assert update.json()["path"] == str(alternate_root.resolve())

    scanned = client.get("/scan_project")
    assert scanned.status_code == 200
    paths = [item["rel_path"] for item in scanned.json()["files"]]
    assert "main.py" in paths


def test_workspace_upload_folder_tree_sets_root(client) -> None:
    uploaded_root = None
    try:
        response = client.post(
            "/workspace/upload",
            files=[
                ("files", ("main.py", b"print('hello')\n", "text/x-python")),
                ("relative_paths", (None, "sample_project/main.py")),
                ("files", ("helper.py", b"def run():\n    return 1\n", "text/x-python")),
                ("relative_paths", (None, "sample_project/pkg/helper.py")),
            ],
        )
        assert response.status_code == 200
        payload = response.json()
        uploaded_root = Path(payload["path"])

        assert uploaded_root.exists()
        assert payload["python_files"] == 2

        scanned = client.get("/scan_project")
        assert scanned.status_code == 200
        listed_paths = [item["rel_path"] for item in scanned.json()["files"]]
        assert "main.py" in listed_paths
        assert "pkg/helper.py" in listed_paths or "pkg\\helper.py" in listed_paths
    finally:
        if uploaded_root and uploaded_root.exists():
            shutil.rmtree(uploaded_root, ignore_errors=True)


def test_validate_fix_and_patch_routes(client) -> None:
    target = client.workspace_root / "buggy.py"
    target.write_text("num = 1\ndenom = 0\nprint(num / denom)\n", encoding="utf-8")

    validate = client.post(
        "/validate_fix",
        json={
            "original": target.read_text(encoding="utf-8"),
            "fixed": "num = 1\ndenom = 0\nif denom != 0:\n    print(num / denom)\nelse:\n    print(0)\n",
            "include_security": False,
        },
    )
    assert validate.status_code == 200
    assert validate.json()["ready_to_apply"] is True

    generate = client.post(
        "/patch/generate",
        json={
            "file_path": str(target),
            "fixed_code": "num = 1\ndenom = 0\nif denom != 0:\n    print(num / denom)\nelse:\n    print(0)\n",
        },
    )
    assert generate.status_code == 200
    assert "@@" in generate.json()["patch"]

    apply = client.post(
        "/patch/apply",
        json={
            "file_path": str(target),
            "fixed_code": "num = 1\ndenom = 0\nif denom != 0:\n    print(num / denom)\nelse:\n    print(0)\n",
            "use_git": False,
        },
    )
    assert apply.status_code == 200
    assert apply.json()["success"] is True
    assert "if denom != 0" in target.read_text(encoding="utf-8")
