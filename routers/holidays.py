from datetime import date
from typing import Literal
from sqlalchemy.exc import SQLAlchemyError
from fastapi import APIRouter, Depends, HTTPException, status, Form
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from database import get_db
from models import Employee, Holiday
from routers.auth import get_current_employee

router = APIRouter(prefix="/holidays",tags=["Holidays"])


# -------------------------
# Schemas
# -------------------------
class HolidayResponse(BaseModel):
    id: int
    name: str
    holiday_date: date
    is_paid: bool
    description: str | None

    model_config = ConfigDict(from_attributes=True)


# -------------------------
# Admin authorization
# -------------------------

def check_admin(user: Employee, db: Session) -> Employee:
    admin = db.query(Employee).filter(Employee.id == user.id).first()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Admin not found")
    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin account is inactive")
    if admin.role != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Super Admin access required")
    return admin

# -------------------------
# Helpers
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
# Create holiday
# -------------------------
@router.post("/",response_model=HolidayResponse,status_code=status.HTTP_201_CREATED)
def create_holiday(name: str = Form(...),
                   holiday_date: date = Form(...),
                   is_paid: bool = Form(...),
                   description: str = Form(...),
                   db: Session = Depends(get_db),
                   user: Employee = Depends(get_current_employee)):
    check_admin(user, db)
    if not name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Holiday name cannot be empty")
    if not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Description cannot be empty")
    existing_holiday = db.query(Holiday).filter(Holiday.holiday_date == holiday_date).first()
    if existing_holiday:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="A holiday already exists on this date")
    holiday = Holiday(name=name.strip(),
                      holiday_date=holiday_date,
                      is_paid=is_paid,
                      description=description.strip())
    try:
        db.add(holiday)
        db.commit()
        db.refresh(holiday)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to create holiday")
    return holiday



# -------------------------
# Get all holidays
# -------------------------

@router.get("/", response_model=list[HolidayResponse])
def get_holidays(db: Session = Depends(get_db),
                 user: Employee = Depends(get_current_employee)):
    return (db.query(Holiday).order_by(Holiday.holiday_date.asc()).all())

# -------------------------
# Get holiday by ID
# -------------------------

@router.get("/{holiday_id}", response_model=HolidayResponse)
def get_holiday(holiday_id: int,db: Session = Depends(get_db),
                user: Employee = Depends(get_current_employee)):
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if holiday is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Holiday not found")
    return holiday


# -------------------------
# Update holiday
# -------------------------

@router.put("/holidays/{holiday_id}")
def update_holiday(holiday_id: int,
                   name: str | None = Form(None),
                   holiday_date: str | None = Form(None),
                   is_paid: Literal["", "true", "false"] | None = Form(None),
                   description: str | None = Form(None),
                   db: Session = Depends(get_db),
                   current_user: Employee = Depends(get_current_employee)):
    check_admin(current_user, db)
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if holiday is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Holiday not found")
    changed = False

    if (value := clean(name)):
        holiday.name = value
        changed = True


    if (value := clean(holiday_date)):
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Holiday date must use YYYY-MM-DD format")
        duplicate = db.query(Holiday).filter(Holiday.holiday_date == parsed_date,Holiday.id != holiday.id).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Another holiday already exists on this date",)
        holiday.holiday_date = parsed_date
        changed = True

    if (value := clean(is_paid)):
        holiday.is_paid = value.lower() == "true"
        changed = True

    if (value := clean(description)):
        holiday.description = value
        changed = True

    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No fields provided to update")

    try:
        db.commit()
        db.refresh(holiday)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to update holiday")

    # 9. Return updated holiday details
    return {"message": "Holiday updated successfully",
            "holiday": {"id": holiday.id,
                        "name": holiday.name,
                        "holiday_date": holiday.holiday_date,
                        "is_paid": holiday.is_paid,
                        "description": holiday.description}}


# -------------------------
# Delete holiday
# -------------------------

@router.delete("/{holiday_id}")
def delete_holiday(holiday_id: int,
                   db: Session = Depends(get_db),
                   user: Employee = Depends(get_current_employee)):
    check_admin(user, db)
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if holiday is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Holiday not found")
    db.delete(holiday)
    db.commit()
    return {"message": "Holiday deleted successfully"}
