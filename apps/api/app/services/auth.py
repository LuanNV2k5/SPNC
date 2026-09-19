import uuid

import secrets

import hashlib

from datetime import datetime, timezone, timedelta

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from sqlalchemy import select

from fastapi import HTTPException, status



from app.core.config import settings

from app.core.security import verify_password, get_password_hash, create_access_token

from app.models.user import User, RefreshSession, AccountStatus

from app.repositories import auth as auth_repo



def get_token_hash(token: str) -> str:

    return hashlib.sha256(token.encode("utf-8")).hexdigest()



def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:

    user = auth_repo.get_user_by_username(db, username=username)

    if not user:

        return None

    if not verify_password(password, user.password_hash):

        return None

    return user



def create_tokens_for_user(db: Session, user: User, family_id: uuid.UUID = None) -> Tuple[str, str]:

    access_token = create_access_token(

        subject=user.id,

        role=user.role,

        status=user.status,

        must_change_password=user.force_password_change

    )



    raw_refresh_token = secrets.token_urlsafe(32)

    refresh_token_hash = get_token_hash(raw_refresh_token)



    if family_id is None:

        family_id = uuid.uuid4()



    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)



    auth_repo.create_refresh_session(

        db=db,

        user_id=user.id,

        family_id=family_id,

        token_hash=refresh_token_hash,

        expires_at=expires_at

    )



    return access_token, raw_refresh_token



def rotate_refresh_token(db: Session, raw_refresh_token: str) -> Tuple[str, str]:

    token_hash = get_token_hash(raw_refresh_token)



    # Use SELECT FOR UPDATE to handle concurrency (Requirement 11, 32)

    db_session = db.execute(

        select(RefreshSession)

        .where(RefreshSession.token_hash == token_hash)

        .with_for_update()

    ).scalar_one_or_none()



    if not db_session:

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail={"error_code": "REFRESH_INVALID", "message": "Invalid refresh token"}

        )



    user = db_session.user



    if db_session.is_revoked:

        # Reuse detected! Revoke the whole family (Requirement 12)

        auth_repo.revoke_refresh_family(db, db_session.family_id)

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail={"error_code": "REFRESH_REVOKED", "message": "Refresh token was already used. Session revoked."}

        )



    if db_session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail={"error_code": "TOKEN_EXPIRED", "message": "Refresh token expired"}

        )



    if user.status != AccountStatus.ACTIVE.value and user.status != AccountStatus.ACTIVE:

        raise HTTPException(

            status_code=status.HTTP_403_FORBIDDEN,

            detail={"error_code": f"ACCOUNT_{user.status}", "message": "Account is not active"}

        )



    # Valid rotation

    db_session.is_revoked = True

    db.commit()



    # Issue new tokens in same family

    return create_tokens_for_user(db, user, family_id=db_session.family_id)
