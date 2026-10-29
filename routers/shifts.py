from datetime import time
from typing import Literal
from fastapi import APIRouter, Depends, Form, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import get_db
from models import Employee, Shift
from routers.auth import get_current_employee


router = APIRouter(prefix="/shifts",tags=["Shifts"])


# -------------------------
# Response Schema
# -------------------------

class ShiftResponse(BaseModel):
    id: int
    name: str
    start_time: time
    end_time: time
    required_work_minutes: int
    is_overnight: bool
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Clean Helper
# -------------------------

def clean(value: str | None) -> str | None:
    """Return None when the field is empty or just Swagger's placeholder."""
    if value is None:
        return None

    value = value.strip()

    if value == "" or value.lower() == "string":
        return None

    return value


# -------------------------
# Admin Authorization
# -------------------------

def check_admin(user: Employee, db: Session) -> Employee:
    """
    Only an authenticated, active SUPER_ADMIN can access
    admin endpoints.
    """
    admin = db.query(Employee).filter(Employee.id == user.id).first()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Admin not found")
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Admin account is inactive")
    if admin.role != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Super Admin access required")
    return admin


# -------------------------
# Helper: Parse Time
# -------------------------

def parse_shift_time(value: str, field_name: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"{field_name} must use HH:MM or HH:MM:SS format")


# -------------------------
# 1. Create Shift
# -------------------------

@router.post("/",response_model=ShiftResponse,status_code=status.HTTP_201_CREATED)
def create_shift(name: str = Form(...),
                 start_time: str = Form(...),
                 end_time: str = Form(...),
                 required_work_minutes: int = Form(..., gt=0),
                 is_overnight: Literal["true", "false"] = Form(...),
                 db: Session = Depends(get_db),
                 current_user: Employee = Depends(get_current_employee)):
    check_admin(current_user, db)

    # Normalize shift name
    name = name.strip().title()

    if not name or name.lower() == "string":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Shift name cannot be empty")

    # Check duplicate shift name
    existing_shift = db.query(Shift).filter(Shift.name.ilike(name)).first()
    if existing_shift:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A shift with this name already exists")

    # Validate shift times
    parsed_start = parse_shift_time(start_time, "Start time")
    parsed_end = parse_shift_time(end_time, "End time")
    overnight = is_overnight == "true"

    if parsed_start == parsed_end and not overnight:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Start and end times cannot be equal for a non-overnight shift")
    if parsed_end < parsed_start and not overnight:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="End time must be later than start time unless the shift is overnight")

    # Create shift
    shift = Shift(name=name,
                  start_time=parsed_start,
                  end_time=parsed_end,
                  required_work_minutes=required_work_minutes,
                  is_overnight=overnight,
                  is_active=True)
    try:
        db.add(shift)
        db.commit()
        db.refresh(shift)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to create shift")
    return shift


# -------------------------
# 2. Get All Shifts
# -------------------------

@router.get("/", response_model=list[ShiftResponse])
def get_shifts(
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee)):
    return (db.query(Shift).order_by(Shift.start_time.asc(), Shift.id.asc()).all())


# -------------------------
# 3. Get Active Shifts
# -------------------------

@router.get("/active", response_model=list[ShiftResponse])
def get_active_shifts(db: Session = Depends(get_db),current_user: Employee = Depends(get_current_employee)):
    return (db.query(Shift).filter(Shift.is_active.is_(True))
            .order_by(Shift.start_time.asc(), Shift.id.asc()).all())


# -------------------------
# 4. Get Shift by ID
# -------------------------

@router.get("/{shift_id}", response_model=ShiftResponse)
def get_shift(shift_id: int,db: Session = Depends(get_db),
              current_user: Employee = Depends(get_current_employee)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Shift not found")
    return shift


# -------------------------
# 5. Update Shift
# -------------------------

@router.put("/{shift_id}", response_model=ShiftResponse)
def update_shift(shift_id: int,
                 name: str | None = Form(None),
                 start_time: str | None = Form(None),
                 end_time: str | None = Form(None),
                 required_work_minutes: str | None = Form(None),
                 is_overnight: Literal["", "true", "false"] | None = Form(None),
                 db: Session = Depends(get_db),
                 current_user: Employee = Depends(get_current_employee)):
    check_admin(current_user, db)
    # Find shift
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Shift not found")
    changed = False

    # 1. Shift name
    if (value := clean(name)):
        value = value.title()
        duplicate = db.query(Shift).filter(Shift.name.ilike(value),Shift.id != shift_id).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Another shift already uses this name")
        shift.name = value
        changed = True

    # 2. Start time
    if (value := clean(start_time)):
        shift.start_time = parse_shift_time(value, "Start time")
        changed = True

    # 3. End time
    if (value := clean(end_time)):
        shift.end_time = parse_shift_time(value, "End time")
        changed = True

    # 4. Required work minutes
    if (value := clean(required_work_minutes)):
        try:
            minutes = int(value)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Required work minutes must be a valid integer")
        if minutes <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Required work minutes must be greater than zero")
        shift.required_work_minutes = minutes
        changed = True

    # 5. Overnight setting
    if (value := clean(is_overnight)):
        shift.is_overnight = value.lower() == "true"
        changed = True

    # 6. Check whether any field was updated
    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No fields provided to update")

    # 7. Validate final shift times
    if shift.start_time == shift.end_time and not shift.is_overnight:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Start and end times cannot be equal for a non-overnight shift")
    if shift.end_time < shift.start_time and not shift.is_overnight:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="End time must be later than start time unless the shift is overnight")
    # 8. Save changes
    try:
        db.commit()
        db.refresh(shift)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to update shift")
    return shift


# -------------------------
# 6. Deactivate Shift
# -------------------------

@router.patch("/{shift_id}/deactivate")
def deactivate_shift(shift_id: int,
                     db: Session = Depends(get_db),
                     current_user: Employee = Depends(get_current_employee)):
    check_admin(current_user, db)
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Shift not found")
    if not shift.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Shift is already inactive")
    shift.is_active = False
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to deactivate shift")
    return {"message": "Shift deactivated successfully"}


# -------------------------
# 7. Activate Shift
# -------------------------

@router.patch("/{shift_id}/activate")
def activate_shift(shift_id: int,
                   db: Session = Depends(get_db),
                   current_user: Employee = Depends(get_current_employee)):
    check_admin(current_user, db)
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Shift not found")
    if shift.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Shift is already active")
    shift.is_active = True
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to activate shift")
    return {"message": "Shift activated successfully"}
