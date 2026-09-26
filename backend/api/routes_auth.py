# backend/api/routes_auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from backend.database import SessionLocal
from backend.models.user import User
from backend.utils.auth_utils import hash_password, verify_password
from backend.api.auth import create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(body: Credentials):
    if len(body.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == body.email).first():
            raise HTTPException(400, "Email already registered")
        user = User(email=body.email, hashed_password=hash_password(body.password))
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(user.id, user.email)
        return {"token": token, "user": {"id": user.id, "email": user.email}}
    finally:
        db.close()


@router.post("/login")
def login(body: Credentials):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == body.email).first()
        if not user or not verify_password(body.password, user.hashed_password):
            raise HTTPException(401, "Invalid email or password")
        if not user.is_active:
            raise HTTPException(403, "Account inactive")
        token = create_access_token(user.id, user.email)
        return {"token": token, "user": {"id": user.id, "email": user.email}}
    finally:
        db.close()


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
