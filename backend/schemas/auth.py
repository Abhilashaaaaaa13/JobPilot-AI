# backend/schemas/auth.py
# Pydantic schemas — API ke request/response shapes
# Why schemas alag models se?
# Models = DB structure
# Schemas = API structure
# Dono alag hote hain — kabhi kabhi
# DB mein zyada fields hote hain jo
# API response mein nahi bhejne (jaise password)

from pydantic import BaseModel,EmailStr

class RegisterRequest(BaseModel):
    email:EmailStr
    password:str

class LoginRequest(BaseModel):
    access_token: str
    token_type: str="bearer"
    user_id :int
    email : str

class UserResponse(BaseModel):
    id : int
    email : str
    is_active : bool

    class Config:
        from_attributes = True
        # Why?
        # SQLAlchemy object directly
        # Pydantic model mein convert ho sake

