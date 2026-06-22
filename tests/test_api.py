# tests/test_api.py
import sys
from datetime import datetime
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    screenshots_dir = str(tmp_path / "screenshots")

    from config import AppConfig, VisionConfig, DatabaseConfig, ServerConfig, DingTalkConfig, AutomationConfig, ScreenshotsConfig
    test_config = AppConfig(
        dingtalk=DingTalkConfig(),
        automation=AutomationConfig(),
        vision=VisionConfig(api_key="test"),
        database=DatabaseConfig(path=db_path),
        server=ServerConfig(),
        screenshots=ScreenshotsConfig(save_dir=screenshots_dir),
    )

    # Mock load_config before importing main so it doesn't try to read config.yaml
    monkeypatch.setattr("config.load_config", lambda path="config.yaml": test_config)

    # Remove main from cache so it re-imports with mocked load_config
    sys.modules.pop("main", None)

    # Mock is_dingtalk_running to avoid tasklist call
    monkeypatch.setattr("automation.window.is_dingtalk_running", lambda: False)

    import main as main_module

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.models import Base

    real_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(real_engine)
    real_session = sessionmaker(bind=real_engine)

    main_module.engine = real_engine
    main_module.SessionLocal = real_session

    from fastapi.testclient import TestClient
    yield TestClient(main_module.app)


def test_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "running"
    assert data["dingtalk_running"] is False


def test_records_empty(client):
    response = client.get("/api/records")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["records"] == []


def test_records_latest_empty(client):
    response = client.get("/api/records/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["record"] is None


def test_daily_summary_empty(client):
    response = client.get("/api/records/daily-summary")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == []


def test_extract_accepts_max_pages(client, monkeypatch):
    import main as main_module

    captured = {}

    class FakeOrchestrator:
        def __init__(self, config, db_session_factory):
            pass

        async def run_extraction(self, max_pages=None):
            captured["max_pages"] = max_pages
            return {
                "status": "ok",
                "pages_scanned": max_pages,
                "records_found": 0,
                "records": [],
            }

    monkeypatch.setattr(main_module, "ExtractOrchestrator", FakeOrchestrator)

    response = client.post("/api/extract", json={"date_range": "all", "max_pages": 2})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["pages_scanned"] == 2
    assert captured["max_pages"] == 2


def test_extract_rejects_invalid_max_pages(client):
    response = client.post("/api/extract", json={"date_range": "all", "max_pages": 0})

    assert response.status_code == 422


def test_seconds_until_next_run(client):
    import main as main_module

    assert main_module.seconds_until_next_run(
        "21:30",
        now=datetime(2026, 6, 22, 21, 0),
    ) == 30 * 60
    assert main_module.seconds_until_next_run(
        "21：30",
        now=datetime(2026, 6, 22, 22, 0),
    ) == 23.5 * 60 * 60
