# backend/utils/auth_utils.py
# Password hashing + JWT token logic

from passlib.context import CryptContext

from datetime import datetime, timedelta
from backend.config import SECRET_KEY, ALGORITHM , TOKEN_EXPIRE_MIN

# Bcrypt context
# Why bcrypt?
# → One way hash — original password recover nahi hota
# → Slow by design — brute force difficult
# → Industry standard
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password:str)->str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed:str)->bool:
    return pwd_context.verify(plain,hashed)



