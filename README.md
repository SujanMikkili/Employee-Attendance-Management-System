# Employee Attendance Management System

A backend application for managing employee records, attendance, work
shifts, leave requests, work-from-home (WFH) requests, holidays, and
attendance-related issues. It is built with **Python**, **FastAPI**,
**SQLAlchemy**, and **PostgreSQL**.

## Features

-   **JWT authentication** and role-based access control for
    `SUPER_ADMIN`, `MANAGER`, and `EMPLOYEE` roles.
-   **Employee management** for employee details, account status,
    manager assignment, and shift assignment.
-   **Attendance tracking** for check-in/check-out, work date, work
    mode, worked time, late time, and overtime.
-   **Shift management** with shift timings, required work duration, and
    overnight-shift support.
-   **Leave management** with leave balances and request statuses such
    as pending, approved, rejected, and cancelled.
-   **WFH requests** with company-level settings for WFH availability,
    approval requirements, advance notice, and monthly limits.
-   **Holiday management** for company holidays.
-   **Attendance conflict tracking** for issues such as missing
    check-outs, attendance during approved leave, and policy violations.
-   **Audit logs** for recording important actions and changes.

> Feature availability depends on the routers and business logic
> implemented in the current codebase. Database models alone do not
> enforce every workflow or approval rule.

## Technology Stack

-   **Language:** Python
-   **Backend framework:** FastAPI
-   **ORM:** SQLAlchemy
-   **Database:** PostgreSQL
-   **Authentication:** JWT
-   **API documentation:** FastAPI Swagger UI

## Project Structure

The exact structure may vary. A typical layout is shown below; keep only
the files and router names that actually exist in your repository.

``` text
employee-attendance-management-system/
├── main.py
├── database.py
├── models.py
├── auth.py
├── routers/
│   ├── admin.py
│   ├── employees.py
│   ├── attendance.py
│   ├── requests.py
│   └── ...
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Prerequisites

-   Python 3.10 or a compatible version for your dependencies
-   PostgreSQL
-   Git (optional, for cloning and version control)

## Setup and Installation

### 1. Clone the repository

``` bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
cd YOUR-REPOSITORY
```

Replace the URL and folder name with your own repository details.

### 2. Create a virtual environment

**Windows:**

``` bash
python -m venv venv
venv\\Scripts\\activate
```

**macOS/Linux:**

``` bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

If the project contains `requirements.txt`:

``` bash
pip install -r requirements.txt
```

Otherwise, install the packages used by your code. Common dependencies
for this stack include:

``` bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv python-jose passlib bcrypt python-multipart
```

Use versions compatible with your code and record tested dependencies in
`requirements.txt`.

### 4. Configure environment variables

Create a `.env` file in the project root. Example:

``` env
DATABASE_URL=postgresql://YOUR_DB_USER:YOUR_DB_PASSWORD@localhost:5432/attendance_system
SECRET_KEY=replace_with_a_long_random_secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

The variable names must match those used by your configuration files.
**Never commit your real `.env` file, database password, or JWT secret
to GitHub.**

### 5. Create the PostgreSQL database

Create a database named `attendance_system`, or update `DATABASE_URL` to
use your database name.

Ensure your application is configured to connect to PostgreSQL. Create
tables using the database initialization or migration approach
configured in your project. If you use Alembic, apply your migrations;
editing `models.py` alone does not automatically update an existing
database schema.

### 6. Run the application

If your FastAPI instance is named `app` in `main.py`, run:

``` bash
uvicorn main:app --reload
```

Adjust the command if your `main.py` path or FastAPI instance name
differs.

## API Documentation

Once the application is running, open:

-   Swagger UI: `http://127.0.0.1:8000/docs`
-   ReDoc: `http://127.0.0.1:8000/redoc`

These pages show the API routes registered with FastAPI and allow you to
test them.

## Database Modules

  -----------------------------------------------------------------------
  Table                               Purpose
  ----------------------------------- -----------------------------------
  `employees`                         Employee details, roles, manager
                                      assignment, and account status

  `company_settings`                  Company attendance, leave, and WFH
                                      rules

  `shifts`                            Shift schedules and required work
                                      duration

  `attendance`                        Daily attendance and
                                      check-in/check-out details

  `leave_balances`                    Allocated and used leave days by
                                      employee, type, and year

  `requests`                          Leave and WFH requests and their
                                      review status

  `holidays`                          Company holiday calendar

  `attendance_conflicts`              Attendance issues requiring review
                                      or resolution

  `audit_logs`                        Records of important actions and
                                      changes
  -----------------------------------------------------------------------

## Security Notes

-   Keep `.env` out of version control.
-   Use a strong, randomly generated `SECRET_KEY`.
-   Do not commit database dumps, production credentials, access tokens,
    or real employee data.
-   Enforce role and ownership checks in protected API endpoints.
-   Use database migrations to manage schema changes safely.

## Current Status

This is a backend project under development. Available functionality
depends on the endpoints and workflow logic present in the current
codebase.

## Author

**Your Name**

Replace this with your name or profile links if you want to include
them.
