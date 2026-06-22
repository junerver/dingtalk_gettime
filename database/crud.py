# database/crud.py
import re
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from database.models import AttendanceRecord


BUSINESS_FIELDS = (
    "punch_time",
    "punch_result",
    "punch_status",
    "shift_time",
    "punch_method",
    "device_info",
    "notes",
)


def upsert_record(db: Session, data: dict) -> dict:
    if is_invalid_punch_record(data):
        return {"action": "ignored", "record": None, "reason": "invalid_punch"}

    existing = db.query(AttendanceRecord).filter_by(
        employee_name=data.get("employee_name"),
        record_date=data["record_date"],
        punch_type=data["punch_type"],
    ).first()

    if existing:
        if not should_replace_record(existing, data):
            return {
                "action": "skipped",
                "record": existing.to_dict(),
                "reason": "not_preferred_punch_time",
            }

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


def is_invalid_punch_record(record) -> bool:
    text = _combined_record_text(record)
    return "无效" in text


def should_replace_record(existing: AttendanceRecord, incoming: dict) -> bool:
    if is_invalid_punch_record(existing):
        return True

    punch_type = incoming.get("punch_type")
    existing_minutes = _punch_minutes(existing)
    incoming_minutes = _punch_minutes(incoming)

    if incoming_minutes is None:
        return existing_minutes is None and _fills_missing_business_data(existing, incoming)
    if existing_minutes is None:
        return True

    if punch_type == "上班打卡":
        if incoming_minutes < existing_minutes:
            return True
        if incoming_minutes > existing_minutes:
            return False
    elif punch_type == "下班打卡":
        if incoming_minutes > existing_minutes:
            return True
        if incoming_minutes < existing_minutes:
            return False

    return _fills_missing_business_data(existing, incoming)


def _punch_minutes(record) -> int | None:
    value = _record_value(record, "punch_time") or _record_value(record, "punch_result")
    if not value:
        return None

    match = re.search(r"(\d{1,2})[:：](\d{1,2})", str(value))
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _fills_missing_business_data(existing: AttendanceRecord, incoming: dict) -> bool:
    for field in BUSINESS_FIELDS:
        existing_value = _record_value(existing, field)
        incoming_value = _record_value(incoming, field)
        if (existing_value is None or existing_value == "") and incoming_value not in (None, ""):
            return True
    return False


def _combined_record_text(record) -> str:
    fields = (
        "punch_type",
        "punch_time",
        "punch_result",
        "punch_status",
        "shift_time",
        "punch_method",
        "device_info",
        "notes",
    )
    return " ".join(str(_record_value(record, field) or "") for field in fields)


def _record_value(record, field: str):
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


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
