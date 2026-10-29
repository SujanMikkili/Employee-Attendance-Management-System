from datetime import date
from typing import Literal,Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from database import get_db
from models import Employee, Shift
from routers.auth import get_current_employee, get_password_hash
from sqlalchemy import func

router = APIRouter(prefix="/admin",tags=["Admin"])


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================

class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_code: str
    first_name: str
    last_name: str
    email: str
    role: str
    department: str | None = None
    job_title: str | None = None
    shift_id: int | None = None
    manager_id: int | None = None
    date_of_joining: date | None = None
    is_active: bool




# ============================================================
# AUTHORIZATION
# ============================================================

def check_admin(user: Employee, db: Session) -> Employee:
    """
    Only an authenticated, active SUPER_ADMIN can access
    admin endpoints.
    """

    admin = (db.query(Employee).filter(Employee.id == user.id).first())

    if admin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Admin not found")

    if not admin.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Admin account is inactive")

    if admin.role != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="Super Admin access required")
    return admin


# ============================================================
# VALIDATION HELPERS
# ============================================================

def validate_email(email: str) -> str:
    email = email.strip().lower()

    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Email cannot be empty")

    # Keep the Gmail-only rule from your existing code.
    if not email.endswith("@gmail.com"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Email must end with @gmail.com")

    if " " in email or email.count("@") != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Invalid email format")
    return email


def clean(value: str | None) -> str | None:
    """Return None when the field is empty or just Swagger's placeholder."""
    if value is None:
        return None
    value = value.strip()
    if value == "" or value.lower() == "string":
        return None
    return value

def validate_password(password: str) -> str:
    if len(password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Password must contain at least 8 characters")
    # bcrypt has a 72-byte input limit.
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Password must not exceed 72 bytes")
    return password


def normalize_name(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"{field_name} cannot be empty")
    return value.title()


def validate_shift(shift_id: int | None, db: Session) -> None:
    if shift_id is None:
        return
    shift = (db.query(Shift).filter(Shift.id == shift_id,Shift.is_active.is_(True)).first())
    if shift is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Shift not found or inactive")


def validate_manager(manager_id: int | None,db: Session,employee_id: int | None = None) -> None:
    if manager_id is None:
        return
    if employee_id is not None and manager_id == employee_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="An employee cannot be their own manager")
    manager = (db.query(Employee).filter(Employee.id == manager_id,Employee.is_active.is_(True)).first())
    if manager is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Manager not found or inactive")
    if manager.role not in ("MANAGER", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Selected employee is not a manager")


def check_duplicate_employee(db: Session,employee_code: str,email: str,exclude_id: int | None = None) -> None:
    code_query = db.query(Employee).filter(Employee.employee_code == employee_code)
    email_query = db.query(Employee).filter(Employee.email == email)
    if exclude_id is not None:
        code_query = code_query.filter(Employee.id != exclude_id)
        email_query = email_query.filter(Employee.id != exclude_id)
    if code_query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Employee code already exists")
    if email_query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Email already exists")


# ============================================================
# 1. CREATE EMPLOYEE
# POST /admin/employees
# ============================================================


@router.post("/employees",status_code=status.HTTP_201_CREATED)
def create_employee(employee_code: str = Form(""),
                    first_name: str = Form(""),
                    last_name: str = Form(""),
                    email: str = Form(""),
                    password: str = Form(""),
                    role: Literal["","EMPLOYEE", "MANAGER"] = Form(...),
                    department: Literal["","Software Development","Quality Assurance","DevOps and Cloud Engineering",
                    "Data and AI","IT Support","Human Resources","Project Management","Sales and Marketing",
                    "Finance and Accounts","UI/UX and Product Design"] = Form(...),
                    job_title: str  = Form(""),
                    shift_name: Literal["","Morning Shift","Evening Shift"] = Form(...),
                    manager_id: int | None = Form(""),
                    db: Session = Depends(get_db),
                    user: Employee = Depends(get_current_employee)):
    # 1. Only SUPER_ADMIN can create employees
    check_admin(user, db)

    # 2. Find the selected active shift
    shift = (db.query(Shift).filter(Shift.name == shift_name,Shift.is_active.is_(True)).first())

    if shift is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Selected shift does not exist or is inactive")

    # 3. Validate employee details
    employee_code = employee_code.strip().upper()
    if not employee_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Employee code cannot be empty")
    first_name = normalize_name(first_name, "First name")
    last_name = normalize_name(last_name, "Last name")
    email = validate_email(email)
    password = validate_password(password)

    # 4. Check for duplicate employee code or email
    check_duplicate_employee(db,employee_code,email)

    # 5. Validate the manager, if one was selected
    if manager_id is not None:
        validate_manager(manager_id, db)

    # 6. Prepare the optional job title
    if job_title is not None:
        job_title = job_title.strip().title()

    # 7. Create the employee record
    employee = Employee(employee_code=employee_code,first_name=first_name,last_name=last_name,
                        email=email,password_hash=get_password_hash(password),role=role,
                        department=department,job_title=job_title,shift_id=shift.id,
                        manager_id=manager_id)

    # 8. Save the employee to the database
    try:
        db.add(employee)
        db.commit()
        db.refresh(employee)

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Unable to create employee. Please try again.")

    # 9. Return employee details without exposing the password hash
    return {
        "message": "Employee created successfully",
        "employee": {
            "id": employee.id,
            "employee_code": employee.employee_code,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "email": employee.email,
            "role": employee.role,
            "department": employee.department,
            "job_title": employee.job_title,
            "shift_id": employee.shift_id,
            "manager_id": employee.manager_id,
            "date_of_joining": employee.date_of_joining,
            "is_active": employee.is_active,
        },
    }



# ============================================================
# 3. GET EMPLOYEE BY ID
# GET /admin/employees/{employee_id}
# ============================================================

@router.get("/employees/{employee_id}",response_model=EmployeeResponse,status_code=status.HTTP_200_OK)
def get_employee(employee_id: int,db: Session = Depends(get_db),user: Employee = Depends(get_current_employee)):
    check_admin(user, db)
    employee = (db.query(Employee).filter(Employee.id == employee_id).first())
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Employee not found")
    return employee


# ============================================================
# 4. UPDATE EMPLOYEE DETAILS AND STATUS
# PUT /admin/employees/{employee_id}
#
# Use form fields in Swagger.
# Leave a field empty/not supplied to keep its existing value.
# ============================================================

@router.put("/employees/{employee_id}")
def update_employee(
    employee_id: int,
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),

    role: Literal["", "MANAGER", "EMPLOYEE"] | None = Form(None),

    department: Literal["",
        "Software Development",
        "Quality Assurance",
        "DevOps and Cloud Engineering",
        "Data and AI",
        "IT Support",
        "Human Resources",
        "Project Management",
        "Sales and Marketing",
        "Finance and Accounts",
        "UI/UX and Product Design"] | None = Form(None),

    job_title: str | None = Form(None),

    shift_name: Literal["", "Morning Shift", "Evening Shift"] | None = Form(None),

    manager_id: str | None = Form(None),   # str, so a blank value doesn't fail validation
    is_active: Literal["", "true", "false"] | None = Form(None),

    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_employee),
):
    # 1. Only SUPER_ADMIN can access this endpoint
    check_admin(current_user, db)

    # 2. Find the employee to update
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    changed = False  # tracks whether the admin actually sent anything

    # 3. First name
    if (value := clean(first_name)):
        employee.first_name = normalize_name(value, "First name")
        changed = True

    # 4. Last name
    if (value := clean(last_name)):
        employee.last_name = normalize_name(value, "Last name")
        changed = True

    # 5. Role
    if (value := clean(role)):
        value = value.upper()

        if value == "EMPLOYEE":
            has_reports = (
                db.query(Employee)
                .filter(Employee.manager_id == employee.id)
                .first()
            )
            if has_reports:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change this manager to EMPLOYEE while employees report to them",
                )

        employee.role = value
        changed = True

    # 6. Department
    if (value := clean(department)):
        employee.department = value
        changed = True

    # 7. Job title
    if (value := clean(job_title)):
        employee.job_title = normalize_name(value, "Job title")
        changed = True

    # 8. Shift (store the shift's ID, not its name)
    if (value := clean(shift_name)):
        shift = (
            db.query(Shift)
            .filter(Shift.name == value, Shift.is_active.is_(True))
            .first()
        )
        if shift is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected shift does not exist or is inactive",
            )
        employee.shift_id = shift.id
        changed = True

    # 9. Manager
    if (value := clean(manager_id)):
        try:
            parsed_manager_id = int(value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Manager ID must be a valid integer",
            )

        validate_manager(parsed_manager_id, db, employee_id=employee.id)
        employee.manager_id = parsed_manager_id
        changed = True

    # 10. Active status
    if (value := clean(is_active)):
        employee.is_active = value.lower() == "true"
        changed = True

    # 11. Nothing was entered, so don't touch the database
    if not changed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided to update",
        )

    # 12. Save the changes
    try:
        db.commit()
        db.refresh(employee)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update employee",
        )

    # 13. Return updated employee details
    return {
        "message": "Employee updated successfully",
        "employee": {
            "id": employee.id,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "role": employee.role,
            "department": employee.department,
            "job_title": employee.job_title,
            "shift_id": employee.shift_id,
            "manager_id": employee.manager_id,
            "date_of_joining": employee.date_of_joining,
            "is_active": employee.is_active,
        },
    }