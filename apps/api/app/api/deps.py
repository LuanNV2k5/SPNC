import uuid

from typing import Generator, List

from fastapi import Depends, HTTPException, status

from fastapi.security import OAuth2PasswordBearer

from jose import jwt, JWTError

from sqlalchemy.orm import Session



from app.core.config import settings

from app.db.session import get_db

from app.models.user import User, AccountStatus

from app.repositories import auth as auth_repo



oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")



def resolve_user_from_token(db: Session, token: str) -> User:
    """Validates an access token and returns its active user; raises HTTPException (401/403) otherwise.
    Shared by HTTP auth (get_current_user) and WebSocket auth (Phase 09C)."""

    credentials_exception = HTTPException(

        status_code=status.HTTP_401_UNAUTHORIZED,

        detail={"error_code": "TOKEN_INVALID", "message": "Could not validate credentials"},

        headers={"WWW-Authenticate": "Bearer"},

    )

    

    try:

        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

        user_id: str = payload.get("sub")

        if user_id is None:

            raise credentials_exception

        token_type = payload.get("type")

        if token_type != "access":

            raise credentials_exception

    except JWTError:

        raise credentials_exception

        

    user = auth_repo.get_user_by_id(db, user_id=uuid.UUID(user_id))

    if user is None:

        raise credentials_exception

        

    # Authoritative account state check (Requirement 9, 33)

    if user.status == AccountStatus.LOCKED.value or user.status == AccountStatus.LOCKED:

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail={"error_code": "ACCOUNT_LOCKED", "message": "Account is locked"}

        )

    if user.status == AccountStatus.PENDING.value or user.status == AccountStatus.PENDING:

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail={"error_code": "ACCOUNT_PENDING", "message": "Account is pending"}

        )

        

    return user


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    return resolve_user_from_token(db, token)


def require_active_user(current_user: User = Depends(get_current_user)) -> User:

    if current_user.force_password_change:

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail={"error_code": "PASSWORD_CHANGE_REQUIRED", "message": "Must change password before proceeding"}

        )

    return current_user



def require_roles(allowed_roles: List[str]):

    def role_checker(current_user: User = Depends(require_active_user)) -> User:

        user_role = current_user.role.value if hasattr(current_user.role, 'value') else current_user.role
        if user_role not in allowed_roles:

            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail={"error_code": "FORBIDDEN_ROLE", "message": "Insufficient permissions"}

            )

        return current_user

    return role_checker



def require_admin(current_user: User = Depends(require_roles(["ADMIN"]))) -> User:

    return current_user



def require_teacher(current_user: User = Depends(require_roles(["TEACHER"]))) -> User:

    return current_user



def require_student(current_user: User = Depends(require_roles(["STUDENT"]))) -> User:

    return current_user

