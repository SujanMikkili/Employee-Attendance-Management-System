
from datetime import datetime, timedelta, timezone
import os
from database import get_db
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models import Employee

load_dotenv()

router = APIRouter(prefix="/auth",tags=["Authentication"])


# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in your .env file")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"],deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_employee(db: Session,email: str,password: str):
    employee = (db.query(Employee).filter(Employee.email == email).first())
    if not employee:
        return None
    if not verify_password(password, employee.password_hash):
        return None
    if not employee.is_active:
        return None
    return employee


@router.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(),db: Session = Depends(get_db)):
    # OAuth2 form field "username" contains the employee's email.
    employee = authenticate_employee(db=db,email=form_data.username,password=form_data.password)
    if not employee:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect email or password, or inactive account",
                            headers={"WWW-Authenticate": "Bearer"})
    access_token = create_access_token(data={"sub": str(employee.id),"role": employee.role})
    return {"access_token": access_token,
            "token_type": "bearer",
            "employee": {"id": employee.id,
                         "employee_code": employee.employee_code,
                         "first_name": employee.first_name,
                         "last_name": employee.last_name,
                         "email": employee.email,
                         "role": employee.role}}


def get_current_employee(token: str = Depends(oauth2_scheme),db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                          detail="Could not validate credentials",
                                          headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        employee_id = payload.get("sub")
        if employee_id is None:
            raise credentials_exception

        employee_id = int(employee_id)

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    employee = (db.query(Employee).filter(Employee.id == employee_id).first())
    if employee is None or not employee.is_active:
        raise credentials_exception

    return employee


def require_roles(*allowed_roles: str):
    def role_checker(current_employee: Employee = Depends(get_current_employee)):
        if current_employee.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="You do not have permission to perform this action")
        return current_employee

    return role_checker


@router.get("/me")
def get_my_profile(current_employee: Employee = Depends(get_current_employee)):
    return {"id": current_employee.id,
            "employee_code": current_employee.employee_code,
            "first_name": current_employee.first_name,
            "last_name": current_employee.last_name,
            "email": current_employee.email,
            "role": current_employee.role,
            "department": current_employee.department,
            "job_title": current_employee.job_title,
            "is_active": current_employee.is_active}
