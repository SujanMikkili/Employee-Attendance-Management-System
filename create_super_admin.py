import re
from getpass import getpass
from datetime import date
from sqlalchemy.orm import Session
from database import SessionLocal,get_db
from models import Employee, Shift
from routers.auth import get_password_hash


def create_super_admin():
    db: Session = SessionLocal()

    try:
        print("\n=== Create Super Admin ===\n")

        employee_code = input("Employee code: ").strip().upper()
        first_name = input("First name: ").strip().title()
        last_name = input("Last name: ").strip().title()
        email = input("Email: ").strip().lower()

        if not all([employee_code, first_name, last_name, email]):
            print("Error: All fields are required.")
            return

        if not email.endswith("@gmail.com") or len(email) <= len("@gmail.com"):
            print("Error: Enter an email address ending with @gmail.com.")
            return

        existing = db.query(Employee).filter(
            (Employee.email == email) |
            (Employee.employee_code == employee_code)
        ).first()

        if existing:
            print("Error: An employee with this email or employee code already exists.")
            return

        password = getpass("Create password: ")
        confirm_password = getpass("Confirm password: ")

        if password != confirm_password:
            print("Error: Passwords do not match.")
            return

        # Select shift
        shifts = db.query(Shift).order_by(Shift.id).all()

        if not shifts:
            print("Error: No shifts found in the shifts table.")
            return

        print("\nAvailable shifts:")

        for shift in shifts:
            print(f"Shift ID: {shift.id} - {shift.name}")

        try:
            shift_id = int(input("\nEnter shift ID: ").strip())
        except ValueError:
            print("Error: Enter a valid numeric shift ID.")
            return

        shift = db.query(Shift).filter(Shift.id == shift_id).first()

        if not shift:
            print("Error: Selected shift ID does not exist.")
            return



        if len(password) < 8:
            print("Error: Password must be at least 8 characters long.")
            return

        if len(password.encode("utf-8")) > 72:
            print("Error: Password must not exceed 72 UTF-8 bytes.")
            return

        super_admin = Employee(
            employee_code=employee_code,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=get_password_hash(password),
            role="SUPER_ADMIN",
            shift_id=shift_id,
            date_of_joining=date.today(),
            is_active=True,
            manager_id=None
        )

        db.add(super_admin)
        db.commit()
        db.refresh(super_admin)

        print("\nSuper Admin created successfully!")
        print(f"Employee ID: {super_admin.id}")
        print(f"Employee code: {super_admin.employee_code}")
        print(f"Name: {super_admin.first_name} {super_admin.last_name}")
        print(f"Email: {super_admin.email}")
        print(f"Role: {super_admin.role}")
        print(f"Shift ID: {super_admin.shift_id}")
        print(f"Shift name: {shift.name}")
        print(f"Date of joining: {super_admin.date_of_joining}")

    except Exception as error:
        db.rollback()
        print(f"\nFailed to create Super Admin: {error}")

    finally:
        db.close()


if __name__ == "__main__":
    create_super_admin()
