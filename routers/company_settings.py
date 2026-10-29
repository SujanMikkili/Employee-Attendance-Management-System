
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from models import Employee, CompanySetting
from routers.auth import get_current_employee


router = APIRouter(prefix="/company-settings", tags=["Company Policies"])


# -------------------------
# Response schema
# -------------------------

class CompanySettingResponse(BaseModel):
    id: int
    company_name: str
    timezone: str

    late_grace_minutes: int
    require_check_out: bool
    allow_overtime: bool

    full_day_minutes: int
    half_day_minutes: int
    short_hours_minutes: int

    leave_approval_required: bool
    allow_half_day_leave: bool
    allow_leave_cancellation: bool

    annual_paid_leave_days: int
    monthly_paid_leave_days: float

    wfh_enabled: bool
    wfh_approval_required: bool
    wfh_advance_notice_hours: int
    wfh_monthly_limit_days: int

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Admin authorization
# -------------------------

def check_admin(user: Employee, db: Session) -> Employee:
    admin = db.query(Employee).filter(Employee.id == user.id).first()

    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin not found"
        )

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is inactive"
        )

    if admin.role != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required"
        )

    return admin


# -------------------------
# Helper
# -------------------------

def clean(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()

    if value == "" or value.lower() == "string":
        return None

    return value


# -------------------------
# Create company settings
# -------------------------

@router.post(
    "/",
    response_model=CompanySettingResponse,
    status_code=status.HTTP_201_CREATED
)
def create_company_settings(
    company_name: str = Form("My Company"),
    timezone: str = Form("Asia/Kolkata"),

    late_grace_minutes: int = Form(0),
    require_check_out: bool = Form(True),
    allow_overtime: bool = Form(True),

    full_day_minutes: int = Form(480),
    half_day_minutes: int = Form(240),
    short_hours_minutes: int = Form(360),

    leave_approval_required: bool = Form(True),
    allow_half_day_leave: bool = Form(True),
    allow_leave_cancellation: bool = Form(True),

    annual_paid_leave_days: int = Form(24),
    monthly_paid_leave_days: float = Form(2),

    wfh_enabled: bool = Form(True),
    wfh_approval_required: bool = Form(True),
    wfh_advance_notice_hours: int = Form(24),
    wfh_monthly_limit_days: int = Form(8),

    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee)
):
    check_admin(user, db)

    # Only one company settings record is allowed
    existing_settings = db.query(CompanySetting).first()

    if existing_settings:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Company settings already exist. Use PUT to update them."
        )

    company_name = clean(company_name)
    timezone = clean(timezone)

    if company_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company name cannot be empty"
        )

    if timezone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timezone cannot be empty"
        )

    try:
        ZoneInfo(timezone)
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid company timezone"
        )

    # Validate integer settings
    integer_fields = {
        "late_grace_minutes": late_grace_minutes,
        "full_day_minutes": full_day_minutes,
        "half_day_minutes": half_day_minutes,
        "short_hours_minutes": short_hours_minutes,
        "wfh_advance_notice_hours": wfh_advance_notice_hours,
        "wfh_monthly_limit_days": wfh_monthly_limit_days
    }

    for field, value in integer_fields.items():
        if value < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field} cannot be negative"
            )

    # Validate attendance thresholds
    if not (
        full_day_minutes >= half_day_minutes >= short_hours_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Attendance thresholds must satisfy "
                "full_day_minutes >= half_day_minutes "
                ">= short_hours_minutes"
            )
        )

    # Validate annual paid leave allocation
    if annual_paid_leave_days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Annual paid leave days must be greater than zero"
        )

    # Validate monthly paid leave allocation
    if monthly_paid_leave_days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monthly paid leave days must be greater than zero"
        )

    if monthly_paid_leave_days * 12 > annual_paid_leave_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Monthly paid leave allocation cannot exceed "
                "the annual paid leave limit"
            )
        )

    settings = CompanySetting(
        company_name=company_name,
        timezone=timezone,

        late_grace_minutes=late_grace_minutes,
        require_check_out=require_check_out,
        allow_overtime=allow_overtime,

        full_day_minutes=full_day_minutes,
        half_day_minutes=half_day_minutes,
        short_hours_minutes=short_hours_minutes,

        leave_approval_required=leave_approval_required,
        allow_half_day_leave=allow_half_day_leave,
        allow_leave_cancellation=allow_leave_cancellation,

        annual_paid_leave_days=annual_paid_leave_days,
        monthly_paid_leave_days=monthly_paid_leave_days,

        wfh_enabled=wfh_enabled,
        wfh_approval_required=wfh_approval_required,
        wfh_advance_notice_hours=wfh_advance_notice_hours,
        wfh_monthly_limit_days=wfh_monthly_limit_days
    )

    try:
        db.add(settings)
        db.commit()
        db.refresh(settings)

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create company settings"
        )

    return settings


# -------------------------
# Get company settings
# -------------------------

@router.get("/", response_model=CompanySettingResponse)
def get_company_settings(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee)
):
    check_admin(user, db)

    settings = db.query(CompanySetting).first()

    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company settings not found"
        )

    return settings


# -------------------------
# Update company settings
# -------------------------

@router.put("/", response_model=CompanySettingResponse)
def update_company_settings(
    company_name: str | None = Form(None),
    timezone: str | None = Form(None),

    late_grace_minutes: int | None = Form(None),
    require_check_out: bool | None = Form(None),
    allow_overtime: bool | None = Form(None),

    full_day_minutes: int | None = Form(None),
    half_day_minutes: int | None = Form(None),
    short_hours_minutes: int | None = Form(None),

    leave_approval_required: bool | None = Form(None),
    allow_half_day_leave: bool | None = Form(None),
    allow_leave_cancellation: bool | None = Form(None),

    annual_paid_leave_days: int | None = Form(None),
    monthly_paid_leave_days: float | None = Form(None),

    wfh_enabled: bool | None = Form(None),
    wfh_approval_required: bool | None = Form(None),
    wfh_advance_notice_hours: int | None = Form(None),
    wfh_monthly_limit_days: int | None = Form(None),

    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_employee)
):
    check_admin(user, db)

    settings = db.query(CompanySetting).first()

    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company settings not found"
        )

    changed = False

    if company_name is not None:
        value = clean(company_name)

        if value is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company name cannot be empty"
            )

        settings.company_name = value
        changed = True

    if timezone is not None:
        value = clean(timezone)

        if value is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Timezone cannot be empty"
            )

        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid company timezone"
            )

        settings.timezone = value
        changed = True

    integer_fields = {
        "late_grace_minutes": late_grace_minutes,
        "full_day_minutes": full_day_minutes,
        "half_day_minutes": half_day_minutes,
        "short_hours_minutes": short_hours_minutes,
        "wfh_advance_notice_hours": wfh_advance_notice_hours,
        "wfh_monthly_limit_days": wfh_monthly_limit_days
    }

    for field, value in integer_fields.items():
        if value is not None:
            if value < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field} cannot be negative"
                )

            setattr(settings, field, value)
            changed = True

    # Update annual paid leave allocation
    if annual_paid_leave_days is not None:
        if annual_paid_leave_days <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Annual paid leave days must be greater than zero"
            )

        settings.annual_paid_leave_days = annual_paid_leave_days
        changed = True

    # Update monthly paid leave allocation
    if monthly_paid_leave_days is not None:
        if monthly_paid_leave_days <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Monthly paid leave days must be greater than zero"
            )

        settings.monthly_paid_leave_days = monthly_paid_leave_days
        changed = True

    # Validate the combined annual and monthly allocation
    if (
        settings.monthly_paid_leave_days * 12
        > settings.annual_paid_leave_days
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Monthly paid leave allocation cannot exceed "
                "the annual paid leave limit"
            )
        )

    boolean_fields = {
        "require_check_out": require_check_out,
        "allow_overtime": allow_overtime,
        "leave_approval_required": leave_approval_required,
        "allow_half_day_leave": allow_half_day_leave,
        "allow_leave_cancellation": allow_leave_cancellation,
        "wfh_enabled": wfh_enabled,
        "wfh_approval_required": wfh_approval_required
    }

    for field, value in boolean_fields.items():
        if value is not None:
            setattr(settings, field, value)
            changed = True

    if not changed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update"
        )

    # Validate attendance thresholds
    if not (
        settings.full_day_minutes
        >= settings.half_day_minutes
        >= settings.short_hours_minutes
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Attendance thresholds must satisfy "
                "full_day_minutes >= half_day_minutes "
                ">= short_hours_minutes"
            )
        )

    try:
        db.commit()
        db.refresh(settings)

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update company settings"
        )

    return settings
