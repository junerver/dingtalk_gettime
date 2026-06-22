# config.py
import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DingTalkConfig:
    path: str = "C:\\Program Files\\DingTalk\\DingTalk.exe"
    launch_wait: int = 10


@dataclass
class AutomationConfig:
    click_delay: float = 1.0
    scroll_delay: float = 2.0
    scroll_amount: int = 5
    scrolls_per_page: int = 5
    max_pages: int = 10
    retry_count: int = 1


@dataclass
class VisionConfig:
    api_base: str = "http://localhost:8000/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 2000


@dataclass
class DatabaseConfig:
    path: str = "./data/attendance.db"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class ScreenshotsConfig:
    save_dir: str = "./data/screenshots"
    keep_days: int = 30


@dataclass
class AppConfig:
    dingtalk: DingTalkConfig = field(default_factory=DingTalkConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    screenshots: ScreenshotsConfig = field(default_factory=ScreenshotsConfig)


def _build_dataclass(cls, data: dict):
    if data is None:
        return cls()
    valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return cls(**filtered)


def load_config(path: str = "config.yaml") -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig(
        dingtalk=_build_dataclass(DingTalkConfig, raw.get("dingtalk")),
        automation=_build_dataclass(AutomationConfig, raw.get("automation")),
        vision=_build_dataclass(VisionConfig, raw.get("vision")),
        database=_build_dataclass(DatabaseConfig, raw.get("database")),
        server=_build_dataclass(ServerConfig, raw.get("server")),
        screenshots=_build_dataclass(ScreenshotsConfig, raw.get("screenshots")),
    )
