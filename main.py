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


# --- Pydantic models ---

class ExtractRequest(BaseModel):
    date_range: str = "all"


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
