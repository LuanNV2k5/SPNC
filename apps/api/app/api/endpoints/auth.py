import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from fastapi.security import OAuth2PasswordRequestForm

from sqlalchemy.orm import Session



from app.db.session import get_db

from app.schemas.auth import LoginResponse, RefreshRequest, UserResponse, PasswordChangeRequest

from app.services import auth as auth_service

from app.repositories import auth as auth_repo

from app.core.security import get_password_hash, verify_password

from app.api.deps import get_current_user

from app.models.user import User, AccountStatus



from app.core.config import settings
from app.services.login_throttle import login_throttle

router = APIRouter()



@router.post("/login", response_model=LoginResponse)

def login(request: Request, db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):

    # OQ-02 (docs/41 R1): checked before the password so a blocked client learns nothing
    client_ip = request.client.host if request.client else "-"
    if login_throttle.is_blocked(form_data.username, client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error_code": "LOGIN_RATE_LIMITED", "message": "Too many failed logins; try again later"},
            headers={"Retry-After": str(settings.LOGIN_WINDOW_SECONDS)},
        )

    user = auth_service.authenticate_user(db, form_data.username, form_data.password)

    if not user:

        login_throttle.record_failure(form_data.username, client_ip)

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail={"error_code": "INVALID_CREDENTIALS", "message": "Incorrect username or password"}

        )

    if user.status != AccountStatus.ACTIVE.value and user.status != AccountStatus.ACTIVE:

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail={"error_code": f"ACCOUNT_{user.status}", "message": "Account is not active"}

        )



    login_throttle.reset(form_data.username, client_ip)
    access_token, refresh_token = auth_service.create_tokens_for_user(db, user)

    return {

        "access_token": access_token,

        "token_type": "bearer",

        "refresh_token": refresh_token

    }



@router.post("/refresh", response_model=LoginResponse)

def refresh(request: RefreshRequest, db: Session = Depends(get_db)):

    access_token, refresh_token = auth_service.rotate_refresh_token(db, request.refresh_token)

    return {

        "access_token": access_token,

        "token_type": "bearer",

        "refresh_token": refresh_token

    }



@router.post("/logout")

def logout(

    request: RefreshRequest,

    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_user)

):

    token_hash = auth_service.get_token_hash(request.refresh_token)

    session = auth_repo.get_refresh_session_by_hash(db, token_hash)

    if session and session.user_id == current_user.id:

        auth_repo.revoke_refresh_session(db, session.id)

    return {"message": "Logged out successfully"}



@router.post("/logout-all")

def logout_all(

    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_user)

):

    auth_repo.revoke_all_user_sessions(db, current_user.id)

    return {"message": "All sessions logged out"}



@router.get("/me", response_model=UserResponse)

def get_me(current_user: User = Depends(get_current_user)):

    return current_user



@router.post("/change-password")

def change_password(

    request: PasswordChangeRequest,

    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_user)

):

    if not verify_password(request.current_password, current_user.password_hash):

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail={"error_code": "CURRENT_PASSWORD_INVALID", "message": "Invalid current password"}

        )



    current_user.password_hash = get_password_hash(request.new_password)

    current_user.force_password_change = False

    auth_repo.revoke_all_user_sessions(db, current_user.id)

    db.commit()



    return {"message": "Password changed successfully"}
