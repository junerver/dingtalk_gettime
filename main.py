# main.py
import logging
import asyncio
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import time as _time
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

last_extract_time: str | None = None
last_scheduled_extract_time: str | None = None
extract_lock = asyncio.Lock()
scheduled_extract_task: asyncio.Task | None = None

request_log: list[dict] = []
request_log_maxlen = 200


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_scheduler()
    try:
        yield
    finally:
        await stop_scheduler()


app = FastAPI(title="钉钉考勤提取服务", version="1.0.0", lifespan=lifespan)

templates = Jinja2Templates(directory='templates')


@app.middleware('http')
async def log_requests(request: Request, call_next):
    start = _time.time()
    response = await call_next(request)
    duration_ms = round((_time.time() - start) * 1000, 1)
    entry = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'method': request.method,
        'path': str(request.url.path),
        'status': response.status_code,
        'duration': duration_ms,
        'client': request.client.host if request.client else None,
    }
    request_log.append(entry)
    if len(request_log) > request_log_maxlen:
        request_log.pop(0)
    return response




@app.get('/', response_class=HTMLResponse)
async def dashboard(request: Request):
    with get_db() as db:
        records = query_records(db)
        total = db.query(AttendanceRecord).count()
    context = {
        'request': request,
        'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'port': config.server.port,
        'dingtalk_running': is_dingtalk_running(),
        'dingtalk_path': config.dingtalk.path,
        'total_records': total,
        'records': [r.to_dict() for r in records[:100]],
        'scheduler_enabled': config.scheduler.enabled,
        'extract_time': config.scheduler.extract_time,
        'last_extract': last_extract_time,
        'last_scheduled': last_scheduled_extract_time,
        'access_logs': request_log[-50:],
        'total_requests': len(request_log),
    }
    return templates.TemplateResponse('dashboard.html', context)


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Pydantic models ---

class ExtractRequest(BaseModel):
    date_range: str = "all"
    max_pages: int | None = Field(default=None, ge=1)
    dry_run: bool = False


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


# --- Routes ---

@app.get("/api/status")
def get_status():
    with get_db() as db:
        total = db.query(AttendanceRecord).count()
    return {
        "status": "running",
        "dingtalk_running": is_dingtalk_running(),
        "last_extract_time": last_extract_time,
        "scheduler": {
            "enabled": config.scheduler.enabled,
            "extract_time": config.scheduler.extract_time,
            "max_pages": config.scheduler.max_pages,
            "last_scheduled_extract_time": last_scheduled_extract_time,
        },
        "total_records": total,
    }


@app.post("/api/extract")
async def extract_attendance(req: ExtractRequest):
    return await run_extract_job(max_pages=req.max_pages, source="manual", dry_run=req.dry_run)


async def run_extract_job(
    max_pages: int | None = None,
    source: str = "manual",
    skip_if_running: bool = False,
    dry_run: bool = False,
) -> dict:
    global last_extract_time, last_scheduled_extract_time

    if extract_lock.locked():
        message = "已有提取任务正在执行"
        if skip_if_running:
            logger.warning(f"{source} 提取任务跳过: {message}")
        return {"status": "busy", "message": message}

    await extract_lock.acquire()
    try:
        orchestrator = ExtractOrchestrator(config, SessionLocal)
        result = await orchestrator.run_extraction(max_pages=max_pages, dry_run=dry_run)
        now = datetime.now().isoformat()
        last_extract_time = now
        if source == "scheduled":
            last_scheduled_extract_time = now
        return result
    except Exception as e:
        logger.exception("提取过程异常")
        return {"status": "error", "message": str(e)}
    finally:
        extract_lock.release()


def seconds_until_next_run(schedule_time: str, now: datetime | None = None) -> float:
    hour, minute = parse_schedule_time(schedule_time)
    current = now or datetime.now()
    target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return (target - current).total_seconds()


def parse_schedule_time(schedule_time: str) -> tuple[int, int]:
    parts = schedule_time.replace("：", ":").split(":")
    if len(parts) != 2:
        raise ValueError(f"定时时间格式无效: {schedule_time}")

    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"定时时间超出范围: {schedule_time}")
    return hour, minute


async def scheduled_extract_loop():
    while True:
        try:
            delay = seconds_until_next_run(config.scheduler.extract_time)
        except ValueError as e:
            logger.error(f"定时提取配置无效，任务已停止: {e}")
            return

        logger.info(
            f"定时提取已启用: 每天 {config.scheduler.extract_time} "
            f"自动提取 {config.scheduler.max_pages} 页"
        )
        await asyncio.sleep(delay)
        logger.info("开始执行定时考勤提取")
        result = await run_extract_job(
            max_pages=config.scheduler.max_pages,
            source="scheduled",
            skip_if_running=True,
        )
        logger.info(f"定时考勤提取完成: {result.get('status')}")


async def start_scheduler():
    global scheduled_extract_task
    if config.scheduler.enabled:
        scheduled_extract_task = asyncio.create_task(scheduled_extract_loop())


async def stop_scheduler():
    global scheduled_extract_task
    if scheduled_extract_task is None:
        return

    scheduled_extract_task.cancel()
    try:
        await scheduled_extract_task
    except asyncio.CancelledError:
        pass
    finally:
        scheduled_extract_task = None


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
    # 强制单进程（workers=1）。uvicorn 在 workers 为 None 时会读取环境变量的
    # WEB_CONCURRENCY；若该变量被设为 >1（部分机器/PM2 环境默认会设置），
    # uvicorn 会派生 worker 子进程，导致 PM2 只跟踪不绑端口的父进程，
    # 重启时子进程成为孤儿占用 8345 端口，进而引发绑定失败->崩溃重启循环。
    # 本项目由 PM2 负责进程管理，不应再让 uvicorn 自己多进程，故显式写死 1。
    uvicorn.run(app, host=config.server.host, port=config.server.port, workers=1)
