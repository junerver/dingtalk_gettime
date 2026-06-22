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
