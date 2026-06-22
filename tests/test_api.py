# tests/test_api.py
import sys
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
