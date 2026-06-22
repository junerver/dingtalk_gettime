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
