from pydantic import BaseModel, EmailStr
from typing import Optional  # 或者直接使用 str | None

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_admin: bool

    class Config:
        from_attributes = True # Pydantic v2, or orm_mode = True for v1

class TokenData(BaseModel):
    username: Optional[str] = None