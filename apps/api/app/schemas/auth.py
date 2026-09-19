from pydantic import BaseModel, EmailStr, ConfigDict

from typing import Optional

import uuid



class Token(BaseModel):

    access_token: str

    token_type: str = "bearer"



class TokenPayload(BaseModel):

    sub: Optional[str] = None

    role: Optional[str] = None

    status: Optional[str] = None

    mcp: Optional[bool] = None



class LoginResponse(Token):

    refresh_token: str



class RefreshRequest(BaseModel):

    refresh_token: str



class PasswordChangeRequest(BaseModel):

    current_password: str

    new_password: str



class UserResponse(BaseModel):

    id: uuid.UUID

    username: str

    email: EmailStr

    full_name: str

    role: str

    status: str

    force_password_change: bool



    model_config = ConfigDict(from_attributes=True)
