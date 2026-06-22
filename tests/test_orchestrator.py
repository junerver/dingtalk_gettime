import pytest

from config import (
    AppConfig,
    AutomationConfig,
    DatabaseConfig,
    DingTalkConfig,
    ScreenshotsConfig,
    ServerConfig,
    VisionConfig,
)
from extractor import orchestrator as orchestrator_module
from extractor.orchestrator import ExtractOrchestrator


class FakeVision:
    def __init__(self, results):
        self.results = list(results)

    async def extract_from_image(self, base64_img):
        return self.results.pop(0)


class FakeScreenshotManager:
    def __init__(self):
        self.saved = 0

    def is_mostly_blank(self, screenshot):
        return False

    def save(self, screenshot):
        self.saved += 1
        return f"screenshot-{self.saved}.png"

    def to_base64(self, screenshot):
        return f"base64-{screenshot}"


class FakeDbSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _make_config(tmp_path, max_pages=3):
    return AppConfig(
        dingtalk=DingTalkConfig(),
        automation=AutomationConfig(max_pages=max_pages),
        vision=VisionConfig(api_key="test"),
        database=DatabaseConfig(path=str(tmp_path / "test.db")),
        server=ServerConfig(),
        screenshots=ScreenshotsConfig(save_dir=str(tmp_path / "screenshots")),
    )


def _make_orchestrator(tmp_path, vision_results):
    orch = ExtractOrchestrator(_make_config(tmp_path), db_session_factory=FakeDbSession)
    orch.vision = FakeVision(vision_results)
    orch.screenshot_mgr = FakeScreenshotManager()
    orch._prepare_work_notification = lambda window: None
    return orch


@pytest.mark.asyncio
async def test_run_extraction_scrolls_when_model_says_no_more(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "activate_dingtalk", lambda path, wait: object())
    orch = _make_orchestrator(
        tmp_path,
        [
            {"records": [], "has_more": False, "page_reached_top": True},
            {"records": [], "has_more": False, "page_reached_top": True},
        ],
    )
    orch.config.automation.max_pages = 2
    captures = iter(["page-1", "page-2"])
    scroll_calls = []

    orch._capture_content = lambda window: next(captures)

    def fake_scroll_page(window, screenshot):
        scroll_calls.append(screenshot)
        return True

    orch._scroll_page = fake_scroll_page

    result = await orch.run_extraction()

    assert result["status"] == "ok"
    assert result["pages_scanned"] == 2
    assert scroll_calls == ["page-1"]


@pytest.mark.asyncio
async def test_run_extraction_uses_requested_max_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "activate_dingtalk", lambda path, wait: object())
    orch = _make_orchestrator(
        tmp_path,
        [
            {"records": [], "has_more": True, "page_reached_top": False},
            {"records": [], "has_more": True, "page_reached_top": False},
        ],
    )
    orch.config.automation.max_pages = 5
    captures = iter(["page-1", "page-2"])
    scroll_calls = []

    orch._capture_content = lambda window: next(captures)

    def fake_scroll_page(window, screenshot):
        scroll_calls.append(screenshot)
        return True

    orch._scroll_page = fake_scroll_page

    result = await orch.run_extraction(max_pages=2)

    assert result["status"] == "ok"
    assert result["pages_scanned"] == 2
    assert scroll_calls == ["page-1"]


@pytest.mark.asyncio
async def test_run_extraction_caps_requested_pages_by_config(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "activate_dingtalk", lambda path, wait: object())
    orch = _make_orchestrator(
        tmp_path,
        [
            {"records": [], "has_more": True, "page_reached_top": False},
            {"records": [], "has_more": True, "page_reached_top": False},
        ],
    )
    orch.config.automation.max_pages = 2
    captures = iter(["page-1", "page-2"])
    scroll_calls = []

    orch._capture_content = lambda window: next(captures)

    def fake_scroll_page(window, screenshot):
        scroll_calls.append(screenshot)
        return True

    orch._scroll_page = fake_scroll_page

    result = await orch.run_extraction(max_pages=10)

    assert result["status"] == "ok"
    assert result["pages_scanned"] == 2
    assert scroll_calls == ["page-1"]


@pytest.mark.asyncio
async def test_run_extraction_stops_when_scroll_does_not_change_screenshot(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "activate_dingtalk", lambda path, wait: object())
    orch = _make_orchestrator(
        tmp_path,
        [
            {"records": [], "has_more": True, "page_reached_top": False},
        ],
    )
    orch._capture_content = lambda window: "page-1"
    scroll_calls = []

    def fake_scroll_page(window, screenshot):
        scroll_calls.append(screenshot)
        return False

    orch._scroll_page = fake_scroll_page

    result = await orch.run_extraction()

    assert result["status"] == "ok"
    assert result["pages_scanned"] == 1
    assert scroll_calls == ["page-1"]


@pytest.mark.asyncio
async def test_run_extraction_stops_after_duplicate_page_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator_module, "activate_dingtalk", lambda path, wait: object())
    upsert_actions = []

    def fake_upsert_record(db, record_data):
        upsert_actions.append(record_data["record_date"])
        return {"action": "skipped", "record": record_data}

    monkeypatch.setattr(orchestrator_module, "upsert_record", fake_upsert_record)
    orch = _make_orchestrator(
        tmp_path,
        [
            {
                "records": [
                    {
                        "record_date": "2026-06-20",
                        "punch_type": "上班打卡",
                        "punch_time": "08:00",
                    }
                ],
                "has_more": True,
                "page_reached_top": False,
            },
            {
                "records": [
                    {
                        "record_date": "2026-06-19",
                        "punch_type": "上班打卡",
                        "punch_time": "08:00",
                    }
                ],
                "has_more": True,
                "page_reached_top": False,
            },
        ],
    )
    orch.config.automation.max_pages = 5
    orch.config.automation.duplicate_page_stop_threshold = 2
    captures = iter(["page-1", "page-2"])
    scroll_calls = []

    orch._capture_content = lambda window: next(captures)

    def fake_scroll_page(window, screenshot):
        scroll_calls.append(screenshot)
        return True

    orch._scroll_page = fake_scroll_page

    result = await orch.run_extraction()

    assert result["status"] == "ok"
    assert result["pages_scanned"] == 2
    assert upsert_actions == ["2026-06-20", "2026-06-19"]
    assert scroll_calls == ["page-1"]
