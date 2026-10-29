from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Employee
from routers.auth import (get_current_employee,verify_password,get_password_hash)

router = APIRouter(prefix="/password", tags=["Password"])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(request: ChangePasswordRequest,db: Session = Depends(get_db),
                    current_employee: Employee = Depends(get_current_employee)):
    # Check the current password
    if not verify_password(request.current_password,current_employee.password_hash):
        raise HTTPException(status_code=400,detail="Current password is incorrect")

    # Check that the new password is different
    if verify_password(request.new_password,current_employee.password_hash):
        raise HTTPException(status_code=400,detail="New password must differ from current password")

    # Validate password length for bcrypt
    if not 8 <= len(request.new_password.encode("utf-8")) <= 72:
        raise HTTPException(status_code=400,
                            detail="Password must be at least 8 characters and at most 72 bytes")

    # Hash and save the new password
    current_employee.password_hash = get_password_hash(request.new_password)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500,detail="Unable to change password")
    return {"message": "Password changed successfully"}
