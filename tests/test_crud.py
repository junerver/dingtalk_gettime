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
