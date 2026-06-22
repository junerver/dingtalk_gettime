# tests/test_config.py
import os
import tempfile
import pytest
import yaml
from config import load_config, AppConfig


def test_load_config_reads_yaml():
    cfg_data = {
        "dingtalk": {"path": "C:\\test\\DingTalk.exe", "launch_wait": 5},
        "automation": {"click_delay": 0.5, "scroll_delay": 1.0, "scroll_amount": 5,
                       "scrolls_per_page": 5, "max_pages": 10, "retry_count": 1},
        "vision": {"api_base": "http://localhost:8000/v1", "api_key": "test-key",
                   "model": "gpt-4o", "max_tokens": 2000},
        "database": {"path": "./data/test.db"},
        "server": {"host": "0.0.0.0", "port": 8080},
        "scheduler": {"enabled": True, "extract_time": "21:30", "max_pages": 2},
        "screenshots": {"save_dir": "./data/screenshots", "keep_days": 30},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(cfg_data, f)
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)

    assert isinstance(cfg, AppConfig)
    assert cfg.dingtalk.path == "C:\\test\\DingTalk.exe"
    assert cfg.automation.duplicate_page_stop_threshold == 5
    assert cfg.vision.model == "gpt-4o"
    assert cfg.scheduler.extract_time == "21:30"
    assert cfg.scheduler.max_pages == 2
    assert cfg.server.port == 8080


def test_load_config_defaults():
    cfg_data = {
        "vision": {"api_base": "http://localhost:8000/v1", "api_key": "k", "model": "m"},
        "database": {"path": "./data/test.db"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(cfg_data, f)
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)

    assert cfg.automation.click_delay == 1.0
    assert cfg.automation.max_pages == 20
    assert cfg.server.port == 8345
    assert cfg.scheduler.enabled is True
    assert cfg.scheduler.extract_time == "21:30"
    assert cfg.scheduler.max_pages == 2
