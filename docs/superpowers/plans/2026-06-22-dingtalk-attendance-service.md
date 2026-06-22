# 钉钉考勤打卡提取服务 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在Windows上构建HTTP服务，通过模拟键鼠操作钉钉桌面版，截图+多模态LLM提取考勤数据，持久化存储并提供查询接口。

**Architecture:** FastAPI服务 → pyautogui自动化钉钉 → 截图 → 多模态LLM提取 → SQLite存储。四个核心模块：automation（窗口/键鼠）、capture（截图）、extractor（LLM）、database（存储）。

**Tech Stack:** Python 3.10+, FastAPI, pyautogui, Pillow, SQLAlchemy, SQLite, httpx, PyYAML

---

### Task 1: 项目初始化

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `data/.gitkeep`

- [ ] **Step 1: 创建 requirements.txt**

```
fastapi>=0.110.0
uvicorn>=0.29.0
pyautogui>=0.9.54
pywinctl>=0.4
Pillow>=10.0
sqlalchemy>=2.0
pyyaml>=6.0
httpx>=0.27.0
openai>=1.30.0
python-multipart>=0.0.9
pytest>=8.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2: 创建 config.yaml**

```yaml
dingtalk:
  path: "C:\\Program Files\\DingTalk\\DingTalk.exe"
  launch_wait: 10

automation:
  click_delay: 1.0
  scroll_delay: 2.0
  scroll_amount: 5
  scrolls_per_page: 5
  max_pages: 10
  retry_count: 1

vision:
  api_base: "http://localhost:8000/v1"
  api_key: "your-api-key"
  model: "gpt-4o"
  max_tokens: 2000

database:
  path: "./data/attendance.db"

server:
  host: "0.0.0.0"
  port: 8080

screenshots:
  save_dir: "./data/screenshots"
  keep_days: 30
```

- [ ] **Step 3: 创建目录结构**

```powershell
mkdir -Force data\screenshots
New-Item -ItemType File -Force data\.gitkeep
# 创建各模块 __init__.py
@("automation", "capture", "extractor", "database") | ForEach-Object {
    New-Item -ItemType File -Force "$_\__init__.py"
}
```

- [ ] **Step 4: 安装依赖**

```powershell
pip install -r requirements.txt
```

- [ ] **Step 5: 初始化 git 仓库并提交**

```powershell
git init
git add .
git commit -m "feat: 项目初始化，创建目录结构和依赖配置"
```

---

### Task 2: 配置管理模块

**Files:**
- Create: `config.py`
- Create: `tests\test_config.py`

- [ ] **Step 1: 编写配置模块测试**

```python
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
        "screenshots": {"save_dir": "./data/screenshots", "keep_days": 30},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(cfg_data, f)
        f.flush()
        cfg = load_config(f.name)
    os.unlink(f.name)

    assert isinstance(cfg, AppConfig)
    assert cfg.dingtalk.path == "C:\\test\\DingTalk.exe"
    assert cfg.vision.model == "gpt-4o"
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
    assert cfg.automation.max_pages == 10
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tests\test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: 实现配置模块**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
python -m pytest tests\test_config.py -v
```

Expected: 2 passed

- [ ] **Step 5: 提交**

```powershell
git add config.py tests/test_config.py
git commit -m "feat: 添加配置管理模块，支持YAML配置加载和默认值"
```

---

### Task 3: 数据库模型

**Files:**
- Create: `database\models.py`
- Create: `tests\test_models.py`

- [ ] **Step 1: 编写模型测试**

```python
# tests/test_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database.models import Base, AttendanceRecord


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_record(db_session):
    record = AttendanceRecord(
        employee_name="张三",
        record_date="2026-06-18",
        punch_type="下班打卡",
        punch_time="17:35",
        punch_result="✅ 17:35 下班打卡·成功",
        punch_status="成功",
        shift_time="06月18日 17:30下班",
        punch_method="考勤机打卡",
        device_info="G2门禁机KN6895",
        notes="下班打卡时间已更新到17:35",
    )
    db_session.add(record)
    db_session.commit()

    saved = db_session.query(AttendanceRecord).first()
    assert saved.employee_name == "张三"
    assert saved.punch_time == "17:35"
    assert saved.punch_type == "下班打卡"


def test_unique_constraint_upsert(db_session):
    r1 = AttendanceRecord(
        employee_name="张三", record_date="2026-06-18",
        punch_type="下班打卡", punch_time="17:30", punch_status="成功",
    )
    db_session.add(r1)
    db_session.commit()

    existing = db_session.query(AttendanceRecord).filter_by(
        employee_name="张三", record_date="2026-06-18", punch_type="下班打卡"
    ).first()
    existing.punch_time = "17:35"
    existing.notes = "时间已更新"
    db_session.commit()

    records = db_session.query(AttendanceRecord).all()
    assert len(records) == 1
    assert records[0].punch_time == "17:35"
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tests\test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 实现数据库模型**

```python
# database/models.py
from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_name = Column(String, nullable=True)
    record_date = Column(String, nullable=False)
    punch_type = Column(String, nullable=False)
    punch_time = Column(String, nullable=True)
    punch_result = Column(String, nullable=True)
    punch_status = Column(String, nullable=True)
    shift_time = Column(String, nullable=True)
    punch_method = Column(String, nullable=True)
    device_info = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    raw_text = Column(String, nullable=True)
    screenshot_path = Column(String, nullable=True)
    created_at = Column(String, server_default="CURRENT_TIMESTAMP")
    updated_at = Column(String, server_default="CURRENT_TIMESTAMP")

    __table_args__ = (
        UniqueConstraint("employee_name", "record_date", "punch_type",
                         name="uq_employee_date_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "employee_name": self.employee_name,
            "record_date": self.record_date,
            "punch_type": self.punch_type,
            "punch_time": self.punch_time,
            "punch_result": self.punch_result,
            "punch_status": self.punch_status,
            "shift_time": self.shift_time,
            "punch_method": self.punch_method,
            "device_info": self.device_info,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
python -m pytest tests\test_models.py -v
```

Expected: 2 passed

- [ ] **Step 5: 提交**

```powershell
git add database/models.py tests/test_models.py
git commit -m "feat: 添加考勤记录SQLAlchemy模型，含唯一约束"
```

---

### Task 4: 数据库CRUD操作

**Files:**
- Create: `database\crud.py`
- Create: `database\__init__.py` (导出)
- Create: `tests\test_crud.py`

- [ ] **Step 1: 编写CRUD测试**

```python
# tests/test_crud.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database.models import Base, AttendanceRecord
from database.crud import upsert_record, query_records, get_latest, get_daily_summary


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_record(**kwargs):
    defaults = {
        "employee_name": "张三",
        "record_date": "2026-06-18",
        "punch_type": "下班打卡",
        "punch_time": "17:35",
        "punch_result": "✅ 17:35 下班打卡·成功",
        "punch_status": "成功",
        "shift_time": "06月18日 17:30下班",
        "punch_method": "考勤机打卡",
        "device_info": "G2门禁机KN6895",
        "notes": "",
    }
    defaults.update(kwargs)
    return defaults


def test_upsert_inserts_new(db_session):
    data = _make_record()
    result = upsert_record(db_session, data)
    assert result["action"] == "inserted"
    assert db_session.query(AttendanceRecord).count() == 1


def test_upsert_updates_existing(db_session):
    data = _make_record()
    upsert_record(db_session, data)
    data["punch_time"] = "18:00"
    result = upsert_record(db_session, data)
    assert result["action"] == "updated"
    assert db_session.query(AttendanceRecord).count() == 1
    assert db_session.query(AttendanceRecord).first().punch_time == "18:00"


def test_query_records_by_date_range(db_session):
    for date in ["2026-06-16", "2026-06-17", "2026-06-18"]:
        upsert_record(db_session, _make_record(record_date=date, punch_type="上班打卡"))
        upsert_record(db_session, _make_record(record_date=date, punch_type="下班打卡"))

    results = query_records(db_session, start_date="2026-06-17", end_date="2026-06-18")
    assert len(results) == 4


def test_query_records_by_punch_type(db_session):
    upsert_record(db_session, _make_record(punch_type="上班打卡", punch_time="08:00"))
    upsert_record(db_session, _make_record(punch_type="下班打卡", punch_time="17:35"))

    results = query_records(db_session, punch_type="上班打卡")
    assert len(results) == 1
    assert results[0].punch_time == "08:00"


def test_get_latest(db_session):
    upsert_record(db_session, _make_record(record_date="2026-06-17"))
    upsert_record(db_session, _make_record(record_date="2026-06-18"))

    latest = get_latest(db_session)
    assert latest.record_date == "2026-06-18"


def test_get_daily_summary(db_session):
    upsert_record(db_session, _make_record(
        record_date="2026-06-18", punch_type="上班打卡", punch_time="07:53"))
    upsert_record(db_session, _make_record(
        record_date="2026-06-18", punch_type="下班打卡", punch_time="17:35"))
    upsert_record(db_session, _make_record(
        record_date="2026-06-17", punch_type="上班打卡", punch_time="08:00"))

    summary = get_daily_summary(db_session, start_date="2026-06-17", end_date="2026-06-18")
    assert len(summary) == 2
    day_18 = [s for s in summary if s["date"] == "2026-06-18"][0]
    assert day_18["clock_in"]["time"] == "07:53"
    assert day_18["clock_out"]["time"] == "17:35"
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tests\test_crud.py -v
```

Expected: FAIL — cannot import `crud`

- [ ] **Step 3: 实现CRUD模块**

```python
# database/crud.py
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database.models import AttendanceRecord


def upsert_record(db: Session, data: dict) -> dict:
    existing = db.query(AttendanceRecord).filter_by(
        employee_name=data.get("employee_name"),
        record_date=data["record_date"],
        punch_type=data["punch_type"],
    ).first()

    if existing:
        for key, value in data.items():
            if hasattr(existing, key) and value is not None:
                setattr(existing, key, value)
        existing.updated_at = datetime.now().isoformat()
        db.commit()
        db.refresh(existing)
        return {"action": "updated", "record": existing.to_dict()}
    else:
        record = AttendanceRecord(**{k: v for k, v in data.items()
                                     if hasattr(AttendanceRecord, k)})
        db.add(record)
        db.commit()
        db.refresh(record)
        return {"action": "inserted", "record": record.to_dict()}


def query_records(
    db: Session,
    start_date: str = None,
    end_date: str = None,
    employee: str = None,
    punch_type: str = None,
) -> list[AttendanceRecord]:
    q = db.query(AttendanceRecord)
    if start_date:
        q = q.filter(AttendanceRecord.record_date >= start_date)
    if end_date:
        q = q.filter(AttendanceRecord.record_date <= end_date)
    if employee:
        q = q.filter(AttendanceRecord.employee_name == employee)
    if punch_type:
        q = q.filter(AttendanceRecord.punch_type == punch_type)
    return q.order_by(desc(AttendanceRecord.record_date), AttendanceRecord.punch_type).all()


def get_latest(db: Session) -> AttendanceRecord | None:
    return db.query(AttendanceRecord).order_by(
        desc(AttendanceRecord.record_date), desc(AttendanceRecord.punch_type)
    ).first()


def get_daily_summary(
    db: Session,
    start_date: str = None,
    end_date: str = None,
    employee: str = None,
) -> list[dict]:
    records = query_records(db, start_date=start_date, end_date=end_date, employee=employee)
    days: dict[str, dict] = {}
    for r in records:
        date = r.record_date
        if date not in days:
            days[date] = {"date": date, "clock_in": None, "clock_out": None}
        entry = {"time": r.punch_time, "status": r.punch_status,
                 "method": r.punch_method, "device": r.device_info}
        if r.punch_type == "上班打卡":
            days[date]["clock_in"] = entry
        elif r.punch_type == "下班打卡":
            days[date]["clock_out"] = entry
    return sorted(days.values(), key=lambda d: d["date"], reverse=True)


def init_db(engine):
    from database.models import Base
    Base.metadata.create_all(engine)
```

- [ ] **Step 4: 更新 database\__init__.py 导出**

```python
# database/__init__.py
from database.models import Base, AttendanceRecord
from database.crud import upsert_record, query_records, get_latest, get_daily_summary, init_db

__all__ = ["Base", "AttendanceRecord", "upsert_record", "query_records",
           "get_latest", "get_daily_summary", "init_db"]
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
python -m pytest tests\test_crud.py -v
```

Expected: 6 passed

- [ ] **Step 6: 提交**

```powershell
git add database/ tests/test_crud.py
git commit -m "feat: 实现数据库CRUD，支持upsert、查询、每日汇总"
```

---

### Task 5: 窗口管理模块

**Files:**
- Create: `automation\window.py`
- Create: `automation\__init__.py`

- [ ] **Step 1: 实现窗口管理**

```python
# automation/window.py
import subprocess
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_dingtalk_window():
    """查找钉钉窗口句柄。返回窗口对象或None。"""
    try:
        import pywinctl
        windows = pywinctl.getWindowsWithTitle("钉钉")
        if windows:
            return windows[0]
        # 尝试英文标题
        windows = pywinctl.getWindowsWithTitle("DingTalk")
        if windows:
            return windows[0]
    except Exception as e:
        logger.warning(f"pywinctl查找失败: {e}")
    return None


def is_dingtalk_running() -> bool:
    """检查钉钉进程是否在运行。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq DingTalk.exe"],
            capture_output=True, text=True, timeout=5
        )
        return "DingTalk.exe" in result.stdout
    except Exception:
        return False


def launch_dingtalk(exe_path: str, wait_seconds: int = 10) -> bool:
    """启动钉钉客户端。"""
    if not Path(exe_path).exists():
        logger.error(f"钉钉路径不存在: {exe_path}")
        return False
    try:
        subprocess.Popen([exe_path])
        logger.info(f"正在启动钉钉，等待 {wait_seconds} 秒...")
        time.sleep(wait_seconds)
        return True
    except Exception as e:
        logger.error(f"启动钉钉失败: {e}")
        return False


def activate_dingtalk(exe_path: str, launch_wait: int = 10) -> object:
    """确保钉钉运行并激活窗口，返回窗口对象。"""
    window = find_dingtalk_window()
    if window is None:
        if not is_dingtalk_running():
            if not launch_dingtalk(exe_path, launch_wait):
                return None
            time.sleep(2)
        window = find_dingtalk_window()

    if window is None:
        logger.error("无法找到钉钉窗口")
        return None

    try:
        window.activate()
        time.sleep(0.5)
        logger.info(f"钉钉窗口已激活: {window.title}")
        return window
    except Exception as e:
        logger.error(f"激活窗口失败: {e}")
        return None
```

- [ ] **Step 2: 更新 automation\__init__.py**

```python
# automation/__init__.py
from automation.window import find_dingtalk_window, is_dingtalk_running, launch_dingtalk, activate_dingtalk

__all__ = ["find_dingtalk_window", "is_dingtalk_running", "launch_dingtalk", "activate_dingtalk"]
```

- [ ] **Step 3: 提交**

```powershell
git add automation/
git commit -m "feat: 添加窗口管理模块，支持钉钉查找/启动/激活"
```

---

### Task 6: 键鼠操作控制器

**Files:**
- Create: `automation\controller.py`

- [ ] **Step 1: 实现键鼠操作控制器**

```python
# automation/controller.py
import time
import logging
import pyautogui

logger = logging.getLogger(__name__)

# 禁用pyautogui安全暂停（生产环境可按需开启）
pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True


def click_at(x: int, y: int, delay: float = 1.0):
    """在指定坐标点击。"""
    logger.debug(f"点击坐标: ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(delay)


def scroll_up(amount: int = 5, delay: float = 2.0):
    """向上滚动（查看更早的消息）。正值=向上。"""
    logger.debug(f"向上滚动 {amount} 格")
    pyautogui.scroll(amount)
    time.sleep(delay)


def scroll_down(amount: int = 5, delay: float = 2.0):
    """向下滚动。"""
    logger.debug(f"向下滚动 {amount} 格")
    pyautogui.scroll(-amount)
    time.sleep(delay)


def press_key(key: str, delay: float = 0.5):
    """按下指定键。"""
    logger.debug(f"按键: {key}")
    pyautogui.press(key)
    time.sleep(delay)


def hotkey(*keys: str, delay: float = 0.5):
    """组合键。"""
    logger.debug(f"组合键: {'+'.join(keys)}")
    pyautogui.hotkey(*keys)
    time.sleep(delay)


def get_mouse_position() -> tuple[int, int]:
    """获取当前鼠标位置。"""
    return pyautogui.position()


def wait(seconds: float):
    """等待指定秒数。"""
    time.sleep(seconds)
```

- [ ] **Step 2: 提交**

```powershell
git add automation/controller.py
git commit -m "feat: 添加键鼠操作控制器"
```

---

### Task 7: 截图管理模块

**Files:**
- Create: `capture\screenshot.py`
- Create: `capture\__init__.py`
- Create: `tests\test_screenshot.py`

- [ ] **Step 1: 编写截图模块测试**

```python
# tests/test_screenshot.py
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from capture.screenshot import ScreenshotManager


def test_save_screenshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ScreenshotManager(save_dir=tmpdir)
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="red")
        path = mgr.save(img, prefix="test")
        assert os.path.exists(path)
        assert "test_" in Path(path).name


def test_image_to_base64():
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="blue")
    mgr = ScreenshotManager(save_dir=".")
    b64 = mgr.to_base64(img)
    assert isinstance(b64, str)
    assert len(b64) > 0
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tests\test_screenshot.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现截图管理模块**

```python
# capture/screenshot.py
import base64
import io
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class ScreenshotManager:
    def __init__(self, save_dir: str = "./data/screenshots"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """截取屏幕指定区域。"""
        import pyautogui
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        return screenshot

    def capture_window(self, window) -> Image.Image:
        """截取指定窗口的内容区域。"""
        try:
            rect = window.rect
            # 截取窗口区域，排除标题栏（约30px）
            x = rect.left
            y = rect.top + 30
            width = rect.width
            height = rect.height - 30
            return self.capture_region(x, y, width, height)
        except Exception as e:
            logger.error(f"窗口截图失败: {e}")
            # fallback: 全屏截图
            import pyautogui
            return pyautogui.screenshot()

    def save(self, image: Image.Image, prefix: str = "dingtalk") -> str:
        """保存截图到文件，返回文件路径。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = self.save_dir / filename
        image.save(str(filepath))
        logger.debug(f"截图已保存: {filepath}")
        return str(filepath)

    @staticmethod
    def to_base64(image: Image.Image) -> str:
        """将图片转为base64字符串。"""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def is_mostly_blank(self, image: Image.Image, threshold: float = 0.95) -> bool:
        """检测截图是否大部分为空白。"""
        pixels = list(image.getdata())
        total = len(pixels)
        blank_count = sum(1 for p in pixels if all(c > 240 for c in p[:3]))
        ratio = blank_count / total
        return ratio > threshold
```

- [ ] **Step 4: 更新 capture\__init__.py**

```python
# capture/__init__.py
from capture.screenshot import ScreenshotManager

__all__ = ["ScreenshotManager"]
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
python -m pytest tests\test_screenshot.py -v
```

Expected: 2 passed

- [ ] **Step 6: 提交**

```powershell
git add capture/ tests/test_screenshot.py
git commit -m "feat: 添加截图管理模块，支持窗口截取、保存和base64转换"
```

---

### Task 8: 多模态LLM提取模块

**Files:**
- Create: `extractor\vision.py`
- Create: `extractor\__init__.py`
- Create: `tests\test_vision.py`

- [ ] **Step 1: 编写Vision客户端测试**

```python
# tests/test_vision.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from extractor.vision import VisionExtractor


MOCK_LLM_RESPONSE = json.dumps({
    "records": [
        {
            "punch_type": "下班打卡",
            "punch_time": "17:35",
            "punch_result": "✅ 17:35 下班打卡·成功",
            "punch_status": "成功",
            "shift_time": "06月18日 17:30下班",
            "punch_method": "考勤机打卡",
            "device_info": "G2门禁机KN6895",
            "notes": "下班打卡时间已更新到17:35",
            "record_date": "2026-06-18",
        }
    ],
    "has_more": True,
    "page_reached_top": False,
})


@pytest.mark.asyncio
async def test_extract_from_base64():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = MOCK_LLM_RESPONSE

    with patch.object(extractor.client.chat.completions, "create",
                      new_callable=lambda: AsyncMock, return_value=mock_response):
        result = await extractor.extract_from_image("fake_base64_string")

    assert len(result["records"]) == 1
    assert result["records"][0]["punch_time"] == "17:35"
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_extract_handles_invalid_json():
    extractor = VisionExtractor(
        api_base="http://localhost:8000/v1",
        api_key="test-key",
        model="gpt-4o",
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这不是JSON"

    with patch.object(extractor.client.chat.completions, "create",
                      new_callable=lambda: AsyncMock, return_value=mock_response):
        result = await extractor.extract_from_image("fake_base64")

    assert result["records"] == []
    assert result["has_more"] is False
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tests\test_vision.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现Vision提取模块**

```python
# extractor/vision.py
import json
import logging
import re
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """请分析这张钉钉"工作通知"截图中的考勤打卡信息。
对每条打卡记录，提取以下字段并返回JSON数组：

{
  "records": [
    {
      "punch_type": "上班打卡/下班打卡",
      "punch_time": "HH:MM",
      "punch_result": "完整打卡结果文本",
      "punch_status": "成功/迟到/早退/缺卡",
      "shift_time": "班次时间",
      "punch_method": "打卡方式",
      "device_info": "设备信息",
      "notes": "备注",
      "record_date": "YYYY-MM-DD"
    }
  ],
  "has_more": true/false,
  "page_reached_top": true/false
}

注意：
- has_more 表示上方是否可能还有更多打卡记录
- page_reached_top 表示是否已经看到最早的消息
- 如果截图中没有考勤信息，返回 {"records": [], "has_more": false, "page_reached_top": true}
- 只返回JSON，不要其他文字"""


class VisionExtractor:
    def __init__(self, api_base: str, api_key: str, model: str, max_tokens: int = 2000):
        self.client = AsyncOpenAI(base_url=api_base, api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    async def extract_from_image(self, base64_image: str) -> dict:
        """从base64图片提取考勤数据。返回解析后的dict。"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": EXTRACT_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content
            return self._parse_response(content)
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return {"records": [], "has_more": False, "page_reached_top": True}

    def _parse_response(self, content: str) -> dict:
        """解析LLM返回的JSON。"""
        try:
            # 尝试直接解析
            data = json.loads(content)
        except json.JSONDecodeError:
            # 尝试从markdown代码块中提取JSON
            match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    logger.warning(f"无法解析LLM返回: {content[:200]}")
                    return {"records": [], "has_more": False, "page_reached_top": True}
            else:
                logger.warning(f"无法解析LLM返回: {content[:200]}")
                return {"records": [], "has_more": False, "page_reached_top": True}

        # 确保必要字段存在
        data.setdefault("records", [])
        data.setdefault("has_more", False)
        data.setdefault("page_reached_top", True)
        return data
```

- [ ] **Step 4: 更新 extractor\__init__.py**

```python
# extractor/__init__.py
from extractor.vision import VisionExtractor

__all__ = ["VisionExtractor"]
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
python -m pytest tests\test_vision.py -v
```

Expected: 2 passed

- [ ] **Step 6: 提交**

```powershell
git add extractor/ tests/test_vision.py
git commit -m "feat: 添加多模态LLM提取模块，支持截图识别和JSON解析"
```

---

### Task 9: 提取编排器

**Files:**
- Create: `extractor\orchestrator.py`

- [ ] **Step 1: 实现提取编排器**

```python
# extractor/orchestrator.py
import logging
import time
from datetime import datetime

from sqlalchemy.orm import Session

from automation.window import activate_dingtalk
from automation.controller import scroll_up, wait
from capture.screenshot import ScreenshotManager
from database.crud import upsert_record
from extractor.vision import VisionExtractor

logger = logging.getLogger(__name__)


class ExtractOrchestrator:
    def __init__(self, config, db_session_factory):
        self.config = config
        self.db_session_factory = db_session_factory
        self.screenshot_mgr = ScreenshotManager(save_dir=config.screenshots.save_dir)
        self.vision = VisionExtractor(
            api_base=config.vision.api_base,
            api_key=config.vision.api_key,
            model=config.vision.model,
            max_tokens=config.vision.max_tokens,
        )

    async def run_extraction(self) -> dict:
        """执行完整的考勤数据提取流程。"""
        # 1. 激活钉钉窗口
        window = activate_dingtalk(
            self.config.dingtalk.path,
            self.config.dingtalk.launch_wait,
        )
        if window is None:
            return {"status": "error", "message": "钉钉未运行且启动失败"}

        all_records = []
        pages_scanned = 0

        for page in range(self.config.automation.max_pages):
            logger.info(f"扫描第 {page + 1} 页...")

            # 2. 截图
            screenshot = self.screenshot_mgr.capture_window(window)

            if self.screenshot_mgr.is_mostly_blank(screenshot):
                logger.warning("截图为空白，停止提取")
                break

            # 保存截图
            screenshot_path = self.screenshot_mgr.save(screenshot)
            base64_img = self.screenshot_mgr.to_base64(screenshot)

            # 3. LLM提取
            result = await self.vision.extract_from_image(base64_img)
            records = result.get("records", [])
            pages_scanned += 1

            logger.info(f"本页提取到 {len(records)} 条记录")

            # 4. 入库
            for record_data in records:
                record_data["raw_text"] = str(result)
                record_data["screenshot_path"] = screenshot_path
                with self.db_session_factory() as db:
                    upsert_result = upsert_record(db, record_data)
                    all_records.append(upsert_result["record"])

            # 5. 判断是否继续
            if result.get("page_reached_top") or not result.get("has_more"):
                logger.info("已到达顶部或无更多数据，停止提取")
                break

            # 6. 向上滚动
            for _ in range(self.config.automation.scrolls_per_page):
                scroll_up(
                    amount=self.config.automation.scroll_amount,
                    delay=self.config.automation.scroll_delay / self.config.automation.scrolls_per_page,
                )

            wait(self.config.automation.scroll_delay)

        return {
            "status": "ok",
            "pages_scanned": pages_scanned,
            "records_found": len(all_records),
            "records": all_records,
        }
```

- [ ] **Step 2: 提交**

```powershell
git add extractor/orchestrator.py
git commit -m "feat: 添加提取编排器，串联自动化-截图-LLM-入库完整流程"
```

---

### Task 10: FastAPI服务与路由

**Files:**
- Create: `main.py`
- Create: `tests\test_api.py`

- [ ] **Step 1: 编写API测试**

```python
# tests/test_api.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("""
vision:
  api_base: "http://localhost:8000/v1"
  api_key: "test"
  model: "test"
database:
  path: "{db_path}"
server:
  host: "0.0.0.0"
  port: 8080
""".format(db_path=str(tmp_path / "test.db")), encoding="utf-8")

    with patch("config.load_config") as mock_load:
        from config import AppConfig, VisionConfig, DatabaseConfig, ServerConfig, DingTalkConfig, AutomationConfig, ScreenshotsConfig
        mock_load.return_value = AppConfig(
            dingtalk=DingTalkConfig(),
            automation=AutomationConfig(),
            vision=VisionConfig(api_key="test"),
            database=DatabaseConfig(path=str(tmp_path / "test.db")),
            server=ServerConfig(),
            screenshots=ScreenshotsConfig(save_dir=str(tmp_path / "screenshots")),
        )
        # 重新导入以使用mock配置
        import importlib
        import main as main_module
        importlib.reload(main_module)
        yield TestClient(main_module.app)


def test_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


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
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python -m pytest tests\test_api.py -v
```

Expected: FAIL

- [ ] **Step 3: 实现FastAPI主模块**

```python
# main.py
import logging
from contextlib import contextmanager
from datetime import datetime

from fastapi import FastAPI, Query
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import load_config
from database.models import Base, AttendanceRecord
from database.crud import upsert_record, query_records, get_latest, get_daily_summary
from extractor.orchestrator import ExtractOrchestrator
from automation.window import is_dingtalk_running

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

config = load_config()

engine = create_engine(f"sqlite:///{config.database.path}", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

app = FastAPI(title="钉钉考勤提取服务", version="1.0.0")

last_extract_time: str | None = None


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic 模型 ---

class ExtractRequest(BaseModel):
    date_range: str = "all"  # today, this_week, this_month, all


class RecordResponse(BaseModel):
    id: int
    employee_name: str | None
    record_date: str
    punch_type: str
    punch_time: str | None
    punch_result: str | None
    punch_status: str | None
    shift_time: str | None
    punch_method: str | None
    device_info: str | None
    notes: str | None
    created_at: str | None
    updated_at: str | None


# --- 路由 ---

@app.get("/api/status")
def get_status():
    with get_db() as db:
        total = db.query(AttendanceRecord).count()
    return {
        "status": "running",
        "dingtalk_running": is_dingtalk_running(),
        "last_extract_time": last_extract_time,
        "total_records": total,
    }


@app.post("/api/extract")
async def extract_attendance(req: ExtractRequest):
    global last_extract_time
    orchestrator = ExtractOrchestrator(config, SessionLocal)
    try:
        result = await orchestrator.run_extraction()
        last_extract_time = datetime.now().isoformat()
        return result
    except Exception as e:
        logger.exception("提取过程异常")
        return {"status": "error", "message": str(e)}


@app.get("/api/records")
def list_records(
    start_date: str = Query(None),
    end_date: str = Query(None),
    employee: str = Query(None),
    punch_type: str = Query(None),
):
    with get_db() as db:
        records = query_records(db, start_date=start_date, end_date=end_date,
                                employee=employee, punch_type=punch_type)
        return {
            "total": len(records),
            "records": [r.to_dict() for r in records],
        }


@app.get("/api/records/latest")
def latest_record():
    with get_db() as db:
        record = get_latest(db)
        return {"record": record.to_dict() if record else None}


@app.get("/api/records/daily-summary")
def daily_summary(
    start_date: str = Query(None),
    end_date: str = Query(None),
    employee: str = Query(None),
):
    with get_db() as db:
        summary = get_daily_summary(db, start_date=start_date,
                                    end_date=end_date, employee=employee)
        return {"summary": summary}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.server.host, port=config.server.port)
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
python -m pytest tests\test_api.py -v
```

Expected: 4 passed

- [ ] **Step 5: 提交**

```powershell
git add main.py tests/test_api.py
git commit -m "feat: 实现FastAPI服务，含提取、查询、汇总、状态接口"
```

---

### Task 11: 端到端验证

**Files:**
- Modify: `main.py` (如有需要的修复)

- [ ] **Step 1: 启动服务验证**

```powershell
python main.py
```

Expected: 服务在 http://0.0.0.0:8080 启动

- [ ] **Step 2: 测试状态接口**

```powershell
curl http://localhost:8080/api/status
```

Expected: `{"status":"running","dingtalk_running":false,"last_extract_time":null,"total_records":0}`

- [ ] **Step 3: 测试空查询接口**

```powershell
curl http://localhost:8080/api/records
curl http://localhost:8080/api/records/latest
curl http://localhost:8080/api/records/daily-summary
```

Expected: 各接口返回空数据结构

- [ ] **Step 4: 测试提取接口（需钉钉运行）**

```powershell
curl -X POST http://localhost:8080/api/extract -H "Content-Type: application/json" -d "{\"date_range\":\"all\"}"
```

Expected: 如果钉钉已登录并导航到工作通知，返回提取结果

- [ ] **Step 5: 验证数据已入库**

```powershell
curl http://localhost:8080/api/records
curl http://localhost:8080/api/records/daily-summary
```

Expected: 返回提取到的考勤数据

- [ ] **Step 6: 最终提交**

```powershell
git add .
git commit -m "feat: 完成钉钉考勤提取服务端到端验证"
```
