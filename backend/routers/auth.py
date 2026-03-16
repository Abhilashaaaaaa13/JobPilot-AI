from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.schemas.auth import(
    RegisterRequest, LoginRequest, TokenResponse, UserResponse
)
from backend.utils.auth_utils import(
    hash_password, veriify_password, create_access_token
)
router = APIRouter(prefix="/auth",tags=["auth"])

@router.post("/register", response_model=UserResponse)
def register(req:RegisterRequest, db: Session=Depends(get_db))
    """register new user.
    why check existing email?
    ->duplicate accounts avoid 
    ->email should be unique-used for login"""
    #email already exists?
    existing = db.query(User).filter(User.email==req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail = "Email already registered!"
        )
    user = User(
        email = req.email,
        hashed_password = hash_password(req.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user

@router.post("/login",response_model=TokenResponse)
def login(req: LoginRequest, db:Session = Depends(get_db)):
    """Login->take JWT
    Why same error for wrong email and wrong password?
    ->Secuirty-attacker should not know that if email exists or not"""
    user = db.query(User).filter(User.email==req.email).first
    if not user or not veriify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email for password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is inactive"
        )
    token = create_access_token({
        "user_id":user.id,
        "email":user.email
    })
    return TokenResponse(
        access_token = token,
        user_id = user.id,
        email = user.email
    )
