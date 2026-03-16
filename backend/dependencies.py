# backend/dependencies.py
# get_current_user — har protected route pe use hoga
# Why separate file?
# Poore project mein import hoga ye function
# Ek jagah rakho — baar baar likhne ki zaroorat nahi

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.utils.auth_utils import decode_token

# Ye FastAPI ko batata hai ki token
# /auth/login endpoint se aata hai
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(
        token: str =   Depends(oauth2_scheme),
        db : Session = Depends(get_db)
)->User:
    """On every protected API route this function will run.
    is token valid? -> return user object
    token invalid? -> 401 error"""
    credentials_exception = HTTPException(
        status_code= status.HTTP_401_UNAUTHORIZED,
        detail = "Invalid or expired token",
        headers = {"WW-Authenticate":"Bearer"}
    )
    payload = decode_token(token)
    if not payload:
        raise credentials_exception
    
    user_id = payload.get("user_id")
    if not user_id:
        raise credentials_exception
    
    user = db.query(User).filter(User.id==user_id).first()
    if not user:
        raise credentials_exception
    
    return user