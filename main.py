from fastapi import FastAPI
import models
from database import engine
from routers import auth,admin,password,attendance,holidays,shifts,company_settings,leaves

app=FastAPI()
models.Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(password.router)
app.include_router(attendance.router)
app.include_router(holidays.router)
app.include_router(shifts.router)
app.include_router(company_settings.router)
app.include_router(leaves.router)