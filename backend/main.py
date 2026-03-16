# backend/main.py
# FastAPI app entry point

from fastapi import FastAPI
from backend.database import init_db
from backend.routers import auth

app = FastAPI(
    title= "Job Hunter Agent",
    description = "Agentic AI job hunting system",
    version = "1.0.0"
)
#tables bnao on startup
@app.on_event("startup")
def startup():
    init_db()

#routers register karo
app.include_router(auth.router)

@app.get("/")
def root():
    return {"status":"running"}