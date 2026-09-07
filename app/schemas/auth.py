from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: str | None = None


class User(BaseModel):
    id: str
    email: str
    is_active: bool = True
    tier: str = "free"


class UserCreate(BaseModel):
    email: str
    password: str
