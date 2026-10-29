from sqlalchemy import (Column,Integer,String,Boolean,Date,DateTime,Time,Text,Numeric,
                        ForeignKey,Enum,UniqueConstraint,CheckConstraint,Index,func)
from sqlalchemy.orm import relationship
from database import Base
from datetime import date
from datetime import datetime

# ============================================================
# 1. EMPLOYEES
# ============================================================

class Employee(Base):
    __tablename__ = "employees"
    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Employee details
    employee_code = Column(String(30), unique=True, nullable=False)#
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # EMPLOYEE, MANAGER, or SUPER_ADMIN
    role = Column(String(20), default="EMPLOYEE", nullable=False)

    # Department and job details
    department = Column(String(100), nullable=True)
    job_title = Column(String(100), nullable=True)


    # Assigned work shift
    shift_id = Column(Integer,ForeignKey("shifts.id", ondelete="SET NULL"),nullable=True)

    # Manager or higher authority assigned to this employee
    # NULL for the top-level super admin
    manager_id = Column(Integer,ForeignKey("employees.id", ondelete="SET NULL"),nullable=True)

    # Joining and account status
    date_of_joining = Column(Date, default=date.today, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)

    # Relationships
    shift = relationship("Shift",back_populates="employees")
    manager = relationship("Employee",remote_side=[id],foreign_keys=[manager_id],back_populates="managed_employees")
    managed_employees = relationship("Employee",foreign_keys=[manager_id],back_populates="manager")
    attendance_records = relationship("Attendance",back_populates="employee",cascade="all, delete-orphan")
    leave_balances = relationship("LeaveBalance",back_populates="employee",cascade="all, delete-orphan")
    requests = relationship("Request",back_populates="employee",foreign_keys="Request.employee_id")



# ============================================================
# 2. COMPANY SETTINGS
# ============================================================

class CompanySetting(Base):
    __tablename__ = "company_settings"

    id = Column(Integer, primary_key=True, index=True)

    company_name = Column(String(200), default="My Company", nullable=False)
    timezone = Column(String(100), default="Asia/Kolkata", nullable=False)

    # Attendance rules
    late_grace_minutes = Column(Integer, default=0, nullable=False)
    require_check_out = Column(Boolean, default=True, nullable=False)
    allow_overtime = Column(Boolean, default=True, nullable=False)

    # Daily attendance thresholds (in minutes)
    full_day_minutes = Column(Integer, default=480, nullable=False)
    half_day_minutes = Column(Integer, default=240, nullable=False)
    short_hours_minutes = Column(Integer, default=360, nullable=False)

    # Leave rules
    leave_approval_required = Column(Boolean, default=True, nullable=False)
    allow_half_day_leave = Column(Boolean, default=True, nullable=False)
    allow_leave_cancellation = Column(Boolean, default=True, nullable=False)

    # Leave allocation policy
    annual_paid_leave_days = Column(Integer, default=24, nullable=False)
    monthly_paid_leave_days = Column(Numeric(4, 1), default=2, nullable=False)

    # Work-from-home rules
    wfh_enabled = Column(Boolean, default=True, nullable=False)
    wfh_approval_required = Column(Boolean, default=True, nullable=False)
    wfh_advance_notice_hours = Column(Integer, default=24, nullable=False)
    wfh_monthly_limit_days = Column(Integer, default=8, nullable=False)


    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)


# ============================================================
# 3. SHIFTS
# ============================================================

class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    required_work_minutes = Column(Integer, default=480, nullable=False)
    is_overnight = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    employees = relationship("Employee", back_populates="shift")
    attendance_records = relationship("Attendance", back_populates="shift")


# ============================================================
# 4. ATTENDANCE
# ============================================================

class Attendance(Base):
    __tablename__ = "attendance"

    __table_args__ = (UniqueConstraint("employee_id","work_date",name="uq_attendance_employee_date"),)
    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer,ForeignKey("employees.id", ondelete="CASCADE"),nullable=False)
    shift_id = Column(Integer,ForeignKey("shifts.id", ondelete="SET NULL"),nullable=True)

    work_date = Column(Date, nullable=False)

    check_in_at = Column(DateTime(timezone=True), nullable=True)
    check_out_at = Column(DateTime(timezone=True), nullable=True)

    work_mode = Column(Enum("OFFICE", "WFH", name="work_mode"),default="OFFICE",nullable=False,)

    status = Column(Enum("IN_PROGRESS","COMPLETED","INCOMPLETE","FLAGGED","ABSENT",name="attendance_status"),
                    default="IN_PROGRESS",nullable=False)

    worked_minutes = Column(Integer, default=0, nullable=False)
    late_minutes = Column(Integer, default=0, nullable=False)
    overtime_minutes = Column(Integer, default=0, nullable=False)

    is_finalized = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)

    employee = relationship("Employee", back_populates="attendance_records")
    shift = relationship("Shift", back_populates="attendance_records")
    sessions = relationship("AttendanceSession",back_populates="attendance",cascade="all, delete-orphan")



# ============================================================
# 5. LEAVE BALANCES
# One row per employee, leave type, and year.
# ============================================================

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer,ForeignKey("employees.id", ondelete="CASCADE"),nullable=False)
    leave_type = Column(Enum("PAID","SICK","CASUAL","EARNED",name="balance_leave_type"),nullable=False)
    allocated_days = Column(Numeric(5, 1), default=0, nullable=False)
    used_days = Column(Numeric(5, 1), default=0, nullable=False)
    year = Column(Integer, nullable=False)

    employee = relationship("Employee", back_populates="leave_balances")

    __table_args__ = (
        UniqueConstraint("employee_id","leave_type","year",name="uq_employee_leave_balance_year"),
        CheckConstraint("allocated_days >= 0",name="ck_leave_allocated_nonnegative"),
        CheckConstraint("used_days >= 0",name="ck_leave_used_nonnegative"),
        CheckConstraint("used_days <= allocated_days",name="ck_leave_used_within_allocation"),)


# ============================================================
# 6. LEAVE AND WFH REQUESTS
# ============================================================

class Request(Base):
    __tablename__ = "requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer,ForeignKey("employees.id", ondelete="CASCADE"),nullable=False)
    request_type = Column(Enum("LEAVE", "WFH", name="request_type"),nullable=False)

    leave_type = Column(Enum("PAID","UNPAID","SICK","CASUAL","EARNED",name="request_leave_type"),nullable=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    duration_days = Column(Numeric(4, 1), nullable=True)

    reason = Column(Text, nullable=True)

    status = Column(
        Enum("PENDING","APPROVED","REJECTED","CANCELLED",name="request_status"),default="PENDING",nullable=False)
    is_paid = Column(Boolean, nullable=True)

    approver_id = Column(Integer,ForeignKey("employees.id", ondelete="SET NULL"),nullable=True)
    reviewed_by = Column(Integer,ForeignKey("employees.id", ondelete="SET NULL"),nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_comment = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now(),nullable=False)

    employee = relationship("Employee",back_populates="requests",foreign_keys=[employee_id])
    reviewer = relationship("Employee", foreign_keys=[reviewed_by])
    approver = relationship("Employee",foreign_keys=[approver_id])

    __table_args__ = (CheckConstraint("end_date >= start_date",name="ck_request_dates"),)


# ============================================================
# 7. HOLIDAYS
# ============================================================

class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(200), nullable=False)
    holiday_date = Column(Date, unique=True, nullable=False)

    is_paid = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ============================================================
# 8. ATTENDANCE CONFLICTS
# ============================================================

class AttendanceConflict(Base):
    __tablename__ = "attendance_conflicts"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer,ForeignKey("employees.id", ondelete="CASCADE"),nullable=False)
    attendance_id = Column(Integer,ForeignKey("attendance.id", ondelete="SET NULL"),nullable=True)
    request_id = Column(Integer,ForeignKey("requests.id", ondelete="SET NULL"),nullable=True)

    conflict_type = Column(
        Enum("ATTENDANCE_DURING_LEAVE","MISSING_CHECK_OUT","INCOMPLETE_BREAK","LATE_ARRIVAL","EARLY_EXIT",
             "WFH_POLICY_VIOLATION","OTHER",name="conflict_type"),nullable=False)

    status = Column(
        Enum("OPEN","UNDER_REVIEW","RESOLVED","DISMISSED",name="conflict_status"),default="OPEN",nullable=False)

    description = Column(Text, nullable=False)

    resolved_by = Column(Integer,ForeignKey("employees.id", ondelete="SET NULL"),nullable=True)
    resolution_reason = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    employee = relationship("Employee", foreign_keys=[employee_id])
    attendance = relationship("Attendance")
    request = relationship("Request")
    resolver = relationship("Employee", foreign_keys=[resolved_by])


# ============================================================
# 9. AUDIT LOGS
# ============================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    actor_employee_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="SET NULL"),nullable=True)

    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=True)

    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)

    reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor = relationship("Employee", foreign_keys=[actor_employee_id])



# ============================================================
# 10. ATTENDANCE SESSION
# ============================================================


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(Integer, primary_key=True, index=True)

    attendance_id = Column(Integer,ForeignKey("attendance.id", ondelete="CASCADE"),nullable=False)
    check_in_at = Column(DateTime(timezone=True), nullable=False)
    check_out_at = Column(DateTime(timezone=True), nullable=True)
    worked_minutes = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    attendance = relationship("Attendance",back_populates="sessions")



# ============================================================
# 11. DAILY ATTENDANCE
# ============================================================


class DailyAttendanceStatus(Base):
    __tablename__ = "daily_attendance_status"

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "work_date",
            name="uq_daily_status_employee_date"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(
        Integer,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )
    shift_id = Column(
        Integer,
        ForeignKey("shifts.id", ondelete="SET NULL"),
        nullable=True
    )
    work_date = Column(Date, nullable=False)
    worked_minutes = Column(Integer, default=0, nullable=False)
    required_work_minutes = Column(Integer, default=480, nullable=False)
    late_minutes = Column(Integer, default=0, nullable=False)
    early_checkout_minutes = Column(Integer, default=0, nullable=False)
    overtime_minutes = Column(Integer, default=0, nullable=False)

    status = Column(
        Enum(
            "PRESENT",
            "HALF_DAY",
            "ABSENT",
            "ON_LEAVE",
            "INCOMPLETE",
            "FLAGGED",
            name="daily_attendance_status_type"
        ),
        default="INCOMPLETE",
        nullable=False
    )

    is_finalized = Column(Boolean, default=False, nullable=False)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    employee = relationship("Employee")
    shift = relationship("Shift")




# ============================================================
# 12. LEAVE ACCURAL HISTORY
# ============================================================



class LeaveAccrualHistory(Base):
    __tablename__ = "leave_accrual_history"

    id = Column(Integer, primary_key=True, index=True)

    employee_id = Column(Integer,ForeignKey("employees.id", ondelete="CASCADE"),nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    # Read from company_settings when creating monthly records.
    # No hardcoded default.
    allocated_days = Column(Numeric(5, 1),nullable=False)
    carried_forward_days = Column(Numeric(5, 1),default=0.0,nullable=False)
    used_days = Column(Numeric(5, 1),default=0.0,nullable=False)
    closing_balance = Column(Numeric(5, 1),default=0.0,nullable=False)
    created_at = Column(DateTime,default=datetime.utcnow,nullable=False)
    employee = relationship("Employee")

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "year",
            "month",
            name="uq_leave_accrual_employee_month"
        ),
        CheckConstraint("month BETWEEN 1 AND 12",name="ck_leave_accrual_month"),
        CheckConstraint("year >= 2000",name="ck_leave_accrual_year"),
        CheckConstraint("allocated_days >= 0 AND "
                        "carried_forward_days >= 0 AND "
                        "used_days >= 0 AND "
                        "closing_balance >= 0",
                        name="ck_leave_accrual_nonnegative"),
        CheckConstraint("closing_balance = "
                        "carried_forward_days + allocated_days - used_days",
                        name="ck_leave_accrual_balance"))
