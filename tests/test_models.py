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
