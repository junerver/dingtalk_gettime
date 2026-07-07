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
    scroll_step_delay: float = 0.15
    click_settle_delay: float = 1.0
    scroll_amount: int = 1
    scrolls_per_page: int = 5
    scroll_focus_x_ratio: float = 0.94
    scroll_focus_y_ratio: float = 0.55
    conversation_list_scrolls: int = 8
    conversation_list_scroll_amount: int = 1
    conversation_list_x_ratio: float = 0.27
    conversation_list_y_ratio: float = 0.55
    work_notification_x_ratio: float = 0.27
    work_notification_y_ratio: float = 0.145
    fallback_conversation_x_ratio: float = 0.27
    fallback_conversation_y_ratio: float = 0.22
    bottom_reset_scrolls: int = 12
    bottom_reset_scroll_amount: int = 3
    max_pages: int = 20
    duplicate_page_stop_threshold: int = 5
    retry_count: int = 1


@dataclass
class VisionConfig:
    api_base: str = "http://localhost:8000/v1"
    api_key: str = ""
    model: str = "gpt-4o"
    max_tokens: int = 4000
    parse_retry_count: int = 2
    empty_result_retry_count: int = 1
    image_stitch_max_pages: int = 3


@dataclass
class DatabaseConfig:
    path: str = "./data/attendance.db"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8345


@dataclass
class SchedulerConfig:
    enabled: bool = True
    extract_time: str = "21:30"
    max_pages: int = 2


@dataclass
class ScreenshotsConfig:
    save_dir: str = "./data/screenshots"
    keep_days: int = 30
    content_crop_left_ratio: float = 0.385
    content_crop_top_ratio: float = 0.05
    content_crop_right_ratio: float = 1.0
    content_crop_bottom_ratio: float = 1.0


@dataclass
class AppConfig:
    dingtalk: DingTalkConfig = field(default_factory=DingTalkConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
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
        scheduler=_build_dataclass(SchedulerConfig, raw.get("scheduler")),
        screenshots=_build_dataclass(ScreenshotsConfig, raw.get("screenshots")),
    )
