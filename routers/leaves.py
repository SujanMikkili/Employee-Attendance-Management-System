
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import get_db
from models import (
    Employee,
    Request,
    LeaveBalance,
    Holiday,
    Attendance,
    DailyAttendanceStatus,
    AttendanceConflict,
    AuditLog,
)
from routers.auth import get_current_employee


router = APIRouter(prefix="/leaves", tags=["Leave Management"])


# --------------------------------------------------
# SCHEMAS
# --------------------------------------------------

class LeaveCreate(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: str = Field(min_length=1, max_length=2000)


class LeaveUpdate(BaseModel):
    leave_type: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = None


class LeaveReview(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class LeaveResponse(BaseModel):
    id: int
    employee_id: int
    request_type: str
    leave_type: str | None
    start_date: date
    end_date: date
    duration_days: Decimal | None
    reason: str | None
    status: str
    approver_id: int | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    reviewer_comment: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


ALLOWED_LEAVE_TYPES = {"PAID", "UNPAID", "SICK", "CASUAL", "EARNED"}


# --------------------------------------------------
# COMMON HELPERS
# --------------------------------------------------

def require_active_employee(user: Employee, db: Session) -> Employee:
    employee = db.query(Employee).filter(
        Employee.id == user.id
    ).first()

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    if not employee.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive",
        )

    return employee


def require_manager(user: Employee, db: Session) -> Employee:
    manager = require_active_employee(user, db)

    if manager.role != "MANAGER":
        raise HTTPException(
            status_code=403,
            detail="Manager access required",
        )

    return manager


def calculate_working_days(
    db: Session,
    start_date: date,
    end_date: date,
) -> int:
    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date",
        )

    holiday_dates = {
        item[0]
        for item in db.query(Holiday.holiday_date).filter(
            Holiday.holiday_date >= start_date,
            Holiday.holiday_date <= end_date,
        ).all()
    }

    count = 0
    current_date = start_date

    while current_date <= end_date:
        if (
            current_date.weekday() < 5
            and current_date not in holiday_dates
        ):
            count += 1

        current_date = date.fromordinal(
            current_date.toordinal() + 1
        )

    if count == 0:
        raise HTTPException(
            status_code=400,
            detail="The selected dates contain no working days",
        )

    return count


def write_audit_log(
    db: Session,
    actor_id: int,
    action: str,
    entity_id: int,
    reason: str | None = None,
):
    db.add(
        AuditLog(
            actor_employee_id=actor_id,
            action=action,
            entity_type="REQUEST",
            entity_id=entity_id,
            reason=reason,
        )
    )


def get_employee_request(
    db: Session,
    request_id: int,
    employee_id: int,
) -> Request:
    request = db.query(Request).filter(
        Request.id == request_id,
        Request.employee_id == employee_id,
        Request.request_type == "LEAVE",
    ).first()

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Leave request not found",
        )

    return request


def update_daily_leave_status(
    db: Session,
    request: Request,
    status_value: str,
):
    current_date = request.start_date

    while current_date <= request.end_date:
        if current_date.weekday() < 5:
            holiday_exists = db.query(Holiday.id).filter(
                Holiday.holiday_date == current_date
            ).first()

            if not holiday_exists:
                attendance = db.query(Attendance).filter(
                    Attendance.employee_id == request.employee_id,
                    Attendance.work_date == current_date,
                ).first()

                daily = db.query(DailyAttendanceStatus).filter(
                    DailyAttendanceStatus.employee_id
                    == request.employee_id,
                    DailyAttendanceStatus.work_date == current_date,
                ).first()

                # Existing check-in must not be erased.
                if attendance and (
                    attendance.check_in_at
                    or attendance.check_out_at
                ):
                    conflict = db.query(AttendanceConflict).filter(
                        AttendanceConflict.request_id == request.id,
                        AttendanceConflict.attendance_id == attendance.id,
                        AttendanceConflict.conflict_type
                        == "ATTENDANCE_DURING_LEAVE",
                        AttendanceConflict.status.in_(
                            ["OPEN", "UNDER_REVIEW"]
                        ),
                    ).first()

                    if not conflict:
                        db.add(
                            AttendanceConflict(
                                employee_id=request.employee_id,
                                attendance_id=attendance.id,
                                request_id=request.id,
                                conflict_type="ATTENDANCE_DURING_LEAVE",
                                status="OPEN",
                                description=(
                                    "Attendance activity exists on an "
                                    "approved leave date. Review required."
                                ),
                            )
                        )

                    if attendance.status != "FLAGGED":
                        attendance.status = "FLAGGED"

                    if daily:
                        daily.status = "FLAGGED"
                        daily.notes = (
                            "Attendance activity conflicts with approved leave."
                        )

                elif daily and not daily.is_finalized:
                    daily.status = status_value
                    daily.notes = (
                        "Approved leave request ID "
                        f"{request.id}"
                        if status_value == "ON_LEAVE"
                        else "Leave status updated"
                    )

                elif not daily and status_value == "ON_LEAVE":
                    # Create a daily status only when no check-in exists.
                    db.add(
                        DailyAttendanceStatus(
                            employee_id=request.employee_id,
                            shift_id=(
                                attendance.shift_id if attendance else None
                            ),
                            work_date=current_date,
                            worked_minutes=0,
                            required_work_minutes=(
                                attendance.shift.required_work_minutes
                                if attendance and attendance.shift
                                else 480
                            ),
                            status="ON_LEAVE",
                            is_finalized=False,
                            notes=(
                                "Approved leave request ID "
                                f"{request.id}"
                            ),
                        )
                    )

        current_date = date.fromordinal(
            current_date.toordinal() + 1
        )


# --------------------------------------------------
# 1. CREATE LEAVE REQUEST
# POST /leaves/
# --------------------------------------------------

@router.post(
    "/",
    response_model=LeaveResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_leave_request(
    payload: LeaveCreate,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    employee = require_active_employee(user, db)

    if employee.role == "SUPER_ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Use an employee account to submit personal leave",
        )

    if payload.leave_type not in ALLOWED_LEAVE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid leave type",
        )

    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date",
        )

    if payload.start_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Leave cannot start in the past",
        )

    if not employee.manager_id:
        raise HTTPException(
            status_code=400,
            detail="You must have an assigned manager before applying",
        )

    manager = db.query(Employee).filter(
        Employee.id == employee.manager_id,
        Employee.is_active.is_(True),
        Employee.role == "MANAGER",
    ).first()

    if not manager:
        raise HTTPException(
            status_code=400,
            detail="Your assigned manager is unavailable",
        )

    duration = calculate_working_days(
        db,
        payload.start_date,
        payload.end_date,
    )

    request = Request(
        employee_id=employee.id,
        request_type="LEAVE",
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        duration_days=Decimal(duration),
        reason=payload.reason.strip(),
        status="PENDING",
        approver_id=manager.id,
        is_paid=(payload.leave_type != "UNPAID"),
    )

    try:
        db.add(request)
        db.flush()

        write_audit_log(
            db,
            employee.id,
            "LEAVE_CREATED",
            request.id,
        )

        db.commit()
        db.refresh(request)
        return request

    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# 2. LIST MY LEAVE REQUESTS
# GET /leaves/my-requests
# --------------------------------------------------

@router.get("/my-requests", response_model=list[LeaveResponse])
def get_my_leave_requests(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    employee = require_active_employee(user, db)

    return (
        db.query(Request)
        .filter(
            Request.employee_id == employee.id,
            Request.request_type == "LEAVE",
        )
        .order_by(Request.created_at.desc())
        .all()
    )


# --------------------------------------------------
# 3. READ MY REQUEST BY ID
# GET /leaves/my-requests/{request_id}
# --------------------------------------------------

@router.get(
    "/my-requests/{request_id}",
    response_model=LeaveResponse,
)
def get_my_leave_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    employee = require_active_employee(user, db)

    return get_employee_request(
        db,
        request_id,
        employee.id,
    )


# --------------------------------------------------
# 4. EDIT PENDING REQUEST
# PUT /leaves/my-requests/{request_id}
# --------------------------------------------------

@router.put(
    "/my-requests/{request_id}",
    response_model=LeaveResponse,
)
def update_my_leave_request(
    request_id: int,
    payload: LeaveUpdate,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    employee = require_active_employee(user, db)

    request = get_employee_request(
        db,
        request_id,
        employee.id,
    )

    if request.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Only pending requests can be edited",
        )

    values = payload.model_dump(exclude_unset=True)

    if not values:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one field to update",
        )

    leave_type = values.get("leave_type", request.leave_type)
    start_date = values.get("start_date", request.start_date)
    end_date = values.get("end_date", request.end_date)
    reason = values.get("reason", request.reason)

    if leave_type not in ALLOWED_LEAVE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid leave type",
        )

    if end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date",
        )

    if start_date < date.today():
        raise HTTPException(
            status_code=400,
            detail="Leave cannot start in the past",
        )

    duration = calculate_working_days(
        db,
        start_date,
        end_date,
    )

    old_values = (
        f"leave_type={request.leave_type}, "
        f"start_date={request.start_date}, "
        f"end_date={request.end_date}"
    )

    request.leave_type = leave_type
    request.start_date = start_date
    request.end_date = end_date
    request.duration_days = Decimal(duration)
    request.reason = reason.strip() if reason else None
    request.is_paid = leave_type != "UNPAID"

    # Reassign to the employee's current manager.
    request.approver_id = employee.manager_id

    write_audit_log(
        db,
        employee.id,
        "LEAVE_UPDATED",
        request.id,
        reason=old_values,
    )

    db.commit()
    db.refresh(request)
    return request


# --------------------------------------------------
# 5. WITHDRAW PENDING REQUEST
# DELETE /leaves/my-requests/{request_id}
# --------------------------------------------------

@router.delete(
    "/my-requests/{request_id}",
    response_model=LeaveResponse,
)
def withdraw_my_leave_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    employee = require_active_employee(user, db)

    request = get_employee_request(
        db,
        request_id,
        employee.id,
    )

    if request.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Only pending requests can be withdrawn",
        )

    request.status = "CANCELLED"
    request.reviewer_comment = "Withdrawn by employee"

    write_audit_log(
        db,
        employee.id,
        "LEAVE_WITHDRAWN",
        request.id,
    )

    db.commit()
    db.refresh(request)
    return request


# --------------------------------------------------
# 6. MANAGER: VIEW PENDING REQUESTS
# GET /leaves/manager/pending
# --------------------------------------------------

@router.get(
    "/manager/pending",
    response_model=list[LeaveResponse],
)
def get_manager_pending_requests(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    manager = require_manager(user, db)

    return (
        db.query(Request)
        .filter(
            Request.request_type == "LEAVE",
            Request.approver_id == manager.id,
            Request.status == "PENDING",
        )
        .order_by(Request.created_at.asc())
        .all()
    )


# --------------------------------------------------
# 7. MANAGER: VIEW REQUEST BY ID
# GET /leaves/manager/requests/{request_id}
# --------------------------------------------------

@router.get(
    "/manager/requests/{request_id}",
    response_model=LeaveResponse,
)
def get_manager_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    manager = require_manager(user, db)

    request = db.query(Request).filter(
        Request.id == request_id,
        Request.request_type == "LEAVE",
        Request.approver_id == manager.id,
    ).first()

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Request not found or not assigned to you",
        )

    return request


# --------------------------------------------------
# 8. MANAGER: APPROVE REQUEST
# POST /leaves/manager/requests/{request_id}/approve
# --------------------------------------------------

@router.post(
    "/manager/requests/{request_id}/approve",
    response_model=LeaveResponse,
)
def approve_leave_request(
    request_id: int,
    payload: LeaveReview,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    manager = require_manager(user, db)

    request = db.query(Request).filter(
        Request.id == request_id,
        Request.request_type == "LEAVE",
        Request.approver_id == manager.id,
    ).with_for_update().first()

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Request not found or not assigned to you",
        )

    if request.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Only pending requests can be approved",
        )

    if request.employee_id == manager.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot approve your own leave request",
        )

    employee = db.query(Employee).filter(
        Employee.id == request.employee_id
    ).first()

    if not employee or not employee.is_active:
        raise HTTPException(
            status_code=400,
            detail="The requesting employee is unavailable",
        )

    # This initial version deducts leave from LeaveBalance.
    # UNPAID leave does not consume a paid leave balance.
    if request.leave_type != "UNPAID":
        balance = db.query(LeaveBalance).filter(
            LeaveBalance.employee_id == request.employee_id,
            LeaveBalance.leave_type == request.leave_type,
            LeaveBalance.year == request.start_date.year,
        ).with_for_update().first()

        if not balance:
            raise HTTPException(
                status_code=400,
                detail="No balance exists for this leave type and year",
            )

        requested_days = Decimal(request.duration_days or 0)
        available_days = (
            Decimal(balance.allocated_days)
            - Decimal(balance.used_days)
        )

        if requested_days > available_days:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Insufficient leave balance. "
                    "Automatic paid/unpaid splitting is not enabled yet."
                ),
            )

        balance.used_days = (
            Decimal(balance.used_days) + requested_days
        )

    request.status = "APPROVED"
    request.reviewed_by = manager.id
    request.reviewed_at = datetime.now().astimezone()
    request.reviewer_comment = payload.comment

    update_daily_leave_status(
        db,
        request,
        "ON_LEAVE",
    )

    write_audit_log(
        db,
        manager.id,
        "LEAVE_APPROVED",
        request.id,
        reason=payload.comment,
    )

    db.commit()
    db.refresh(request)
    return request


# --------------------------------------------------
# 9. MANAGER: REJECT REQUEST
# POST /leaves/manager/requests/{request_id}/reject
# --------------------------------------------------

@router.post(
    "/manager/requests/{request_id}/reject",
    response_model=LeaveResponse,
)
def reject_leave_request(
    request_id: int,
    payload: LeaveReview,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee),
):
    manager = require_manager(user, db)

    request = db.query(Request).filter(
        Request.id == request_id,
        Request.request_type == "LEAVE",
        Request.approver_id == manager.id,
    ).with_for_update().first()

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Request not found or not assigned to you",
        )

    if request.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail="Only pending requests can be rejected",
        )

    request.status = "REJECTED"
    request.reviewed_by = manager.id
    request.reviewed_at = datetime.now().astimezone()
    request.reviewer_comment = payload.comment

    write_audit_log(
        db,
        manager.id,
        "LEAVE_REJECTED",
        request.id,
        reason=payload.comment,
    )

    db.commit()
    db.refresh(request)
    return request
