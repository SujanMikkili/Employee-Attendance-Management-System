from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import (Employee,CompanySetting,Shift,Attendance,AttendanceSession,Request)
from routers.auth import get_current_employee

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def get_company_settings(db: Session):
    return db.query(CompanySetting).first()


def get_company_now(settings):
    timezone_name = (settings.timezone if settings else "Asia/Kolkata")
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        raise HTTPException(status_code=500,detail="Invalid company timezone setting")
    return datetime.now(timezone)


def get_shift_datetimes(shift, work_date, timezone):
    if not shift:
        return None, None

    start_at = datetime.combine(work_date, shift.start_time).replace(tzinfo=timezone)
    end_date = work_date

    if shift.is_overnight:
        end_date += timedelta(days=1)
    elif shift.end_time <= shift.start_time:
        end_date += timedelta(days=1)

    end_at = datetime.combine( end_date, shift.end_time).replace(tzinfo=timezone)
    return start_at, end_at


@router.post("/check-in", status_code=status.HTTP_201_CREATED)
def check_in(db: Session = Depends(get_db),current_user: Employee = Depends(get_current_employee)):
    settings = get_company_settings(db)
    now = get_company_now(settings)
    today = now.date()
    # Prevent another check-in while a session is open.
    open_session = (db.query(AttendanceSession).join(Attendance).filter
                    (Attendance.employee_id == current_user.id,
                     AttendanceSession.check_out_at.is_(None)).first())
    if open_session:
        raise HTTPException(status_code=400,
                            detail="Please check out of your current session first")
    attendance = (db.query(Attendance).filter(Attendance.employee_id == current_user.id,
                                              Attendance.work_date == today).first())

    if attendance and attendance.is_finalized:
        raise HTTPException(status_code=400,
                            detail="Attendance for today has already been finalized")

    # Check approved WFH request for today.
    approved_wfh = (db.query(Request)
        .filter(Request.employee_id == current_user.id,
                Request.request_type == "WFH",
                Request.status == "APPROVED",
                Request.start_date <= today,
                Request.end_date >= today).first())
    work_mode = "OFFICE"

    if approved_wfh:
        if settings and not settings.wfh_enabled:
            raise HTTPException(status_code=400,
                                detail="Work from home is currently disabled")
        work_mode = "WFH"

    shift = (db.query(Shift).filter(Shift.id == current_user.shift_id).first()
             if current_user.shift_id else None)
    if not attendance:
        attendance = Attendance(employee_id=current_user.id,
                                shift_id=current_user.shift_id,
                                work_date=today,
                                check_in_at=now,
                                work_mode=work_mode,
                                status="IN_PROGRESS",
                                worked_minutes=0,
                                late_minutes=0,
                                overtime_minutes=0)
        db.add(attendance)
        db.flush()

        # Calculate lateness only for the first check-in.
        if shift:
            timezone = now.tzinfo
            shift_start, _ = get_shift_datetimes(shift, today, timezone)
            grace_minutes = (settings.late_grace_minutes if settings else 0)

            late_minutes = int(max(0,(now - shift_start).total_seconds() / 60 - grace_minutes))
            attendance.late_minutes = late_minutes
    elif attendance.check_in_at is None:
        attendance.check_in_at = now

    # Create a separate session for every check-in.
    session_record = AttendanceSession(
        attendance_id=attendance.id,
        check_in_at=now,
        worked_minutes=0,
    )

    attendance.status = "IN_PROGRESS"
    attendance.check_out_at = None

    db.add(session_record)

    try:
        db.commit()
        db.refresh(attendance)
        db.refresh(session_record)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record check-in",
        )

    return {
        "message": "Check-in successful",
        "attendance_id": attendance.id,
        "session_id": session_record.id,
        "check_in_at": session_record.check_in_at,
        "work_date": attendance.work_date,
        "work_mode": attendance.work_mode,
        "status": attendance.status,
    }


@router.post("/check-out")
def check_out(db: Session = Depends(get_db),current_user: Employee = Depends(get_current_employee)):
    settings = get_company_settings(db)
    now = get_company_now(settings)

    # Find the employee's currently open session.
    session_record = (db.query(AttendanceSession).join(Attendance).filter(Attendance.employee_id == current_user.id,
            AttendanceSession.check_out_at.is_(None))
        .order_by(AttendanceSession.id.desc())
        .first())

    if not session_record:
        raise HTTPException(status_code=400,detail="No active check-in session found")

    attendance = (db.query(Attendance).filter(Attendance.id == session_record.attendance_id).first())

    if not attendance or attendance.is_finalized:
        raise HTTPException(status_code=400,detail="Attendance is unavailable or finalized")

    check_in_at = session_record.check_in_at

    # Normalize timestamps to the same timezone before subtraction.
    if check_in_at.tzinfo is None:
        check_in_at = check_in_at.replace(tzinfo=now.tzinfo)

    if now < check_in_at:
        raise HTTPException(status_code=400,detail="Check-out cannot be before check-in")

    session_minutes = int((now - check_in_at).total_seconds() // 60)

    session_record.check_out_at = now
    session_record.worked_minutes = session_minutes

    # Recalculate the day's total from all completed sessions.
    db.flush()

    completed_sessions = (db.query(AttendanceSession).filter(AttendanceSession.attendance_id == attendance.id,
                                                             AttendanceSession.check_out_at.isnot(None)).all())
    total_worked_minutes = sum(item.worked_minutes for item in completed_sessions)

    attendance.worked_minutes = total_worked_minutes
    attendance.check_out_at = now
    attendance.status = "COMPLETED"

    shift = (db.query(Shift).filter(Shift.id == attendance.shift_id).first() if attendance.shift_id else None)

    # Calculate early checkout for this session's checkout.
    early_checkout_minutes = 0

    if shift:
        timezone = now.tzinfo
        _, shift_end = get_shift_datetimes(shift, attendance.work_date, timezone)

        # For overnight shifts, the end may be on the next day.
        if shift.is_overnight and now.date() > attendance.work_date:
            _, shift_end = get_shift_datetimes(shift, attendance.work_date, timezone)

        if now < shift_end:
            early_checkout_minutes = int((shift_end - now).total_seconds() // 60)

    overtime_minutes = 0

    if settings and settings.allow_overtime and shift:
        overtime_minutes = max(0,total_worked_minutes - shift.required_work_minutes)
    attendance.overtime_minutes = overtime_minutes

    try:
        db.commit()
        db.refresh(attendance)
        db.refresh(session_record)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500,detail="Failed to record check-out")
    return {"message": "Check-out successful",
            "attendance_id": attendance.id,
            "session_id": session_record.id,
            "check_out_at": session_record.check_out_at,
            "session_worked_minutes": session_minutes,
            "total_worked_minutes": attendance.worked_minutes,
            "late_minutes": attendance.late_minutes,
            "early_checkout_minutes": early_checkout_minutes,
            "overtime_minutes": attendance.overtime_minutes,
            "status": attendance.status}
