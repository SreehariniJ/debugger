from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["OFFLINE_DEBUGGER_DISABLE_MODEL"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main
from backend.config import get_workspace_root
from backend.database import Base, get_db
from backend.dependencies import reinitialize_workspace
from backend.utils import _persist_workspace_root


@pytest.fixture(scope="function")
def client(monkeypatch):
    project_root = PROJECT_ROOT
    workspace_root = Path(tempfile.mkdtemp(prefix="test_workspace_", dir=str(project_root)))

    db_fd, db_path = tempfile.mkstemp(suffix=".db", dir=str(project_root))
    os.close(db_fd)

    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    original_workspace = get_workspace_root()
    main.app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(main, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(main, "init_db", lambda: Base.metadata.create_all(bind=test_engine))

    reinitialize_workspace(workspace_root)

    try:
        with TestClient(main.app) as test_client:
            login = test_client.post(
                "/auth/login",
                json={"username": "admin", "password": "admin123"},
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]
            test_client.headers.update({"Authorization": f"Bearer {token}"})
            test_client.workspace_root = workspace_root
            yield test_client
    finally:
        main.app.dependency_overrides.clear()
        reinitialize_workspace(original_workspace)
        _persist_workspace_root(original_workspace)
        test_engine.dispose()
        if os.path.exists(db_path):
            os.unlink(db_path)
        shutil.rmtree(workspace_root, ignore_errors=True)
