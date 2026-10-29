import uuid
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.user import User, AuditLog, RoleEnum, AccountStatus
from app.core.security import get_password_hash
from app.repositories import auth as auth_repo
from app.repositories import admin as admin_repo
from fastapi import HTTPException, status

def log_admin_action(db: Session, actor_id: uuid.UUID, action: str, target_type: str = None, target_id: str = None, request_id: str = None):
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id
    )
    db.add(log)
    db.commit()

def check_last_admin_invariant(db: Session, target_user: User, new_role: str = None, new_status: str = None):
    # This is handled within update_user now to ensure transaction locking order.
    pass

def create_user(db: Session, actor_id: uuid.UUID, username: str, email: str, password: str, full_name: str, role: str) -> User:
    if auth_repo.get_user_by_username(db, username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "USERNAME_ALREADY_EXISTS", "message": "Username exists"}
        )
    if role not in [RoleEnum.ADMIN.value, RoleEnum.TEACHER.value, RoleEnum.STUDENT.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "INVALID_ROLE", "message": "Invalid role"}
        )

    user = User(
        username=username,
        email=email,
        password_hash=get_password_hash(password),
        full_name=full_name,
        role=role,
        status=AccountStatus.ACTIVE.value,
        force_password_change=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_admin_action(db, actor_id, "USER_CREATED", "USER", str(user.id))
    return user

def update_user(db: Session, actor_id: uuid.UUID, user_id: uuid.UUID, role: Optional[str] = None, user_status: Optional[str] = None) -> User:
    try:
        # First read the target user outside lock to know if we need the lock
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "USER_NOT_FOUND", "message": "User not found"}
            )

        is_dangerous = False
        if user.role == RoleEnum.ADMIN.value and user.status == AccountStatus.ACTIVE.value:
            if (role and role != RoleEnum.ADMIN.value) or (user_status and user_status != AccountStatus.ACTIVE.value):
                is_dangerous = True

        if is_dangerous:
            admin_repo.acquire_last_admin_lock(db)
            # Re-read authoritative state
            user = db.query(User).filter(User.id == user_id).first()
            if user.role == RoleEnum.ADMIN.value and user.status == AccountStatus.ACTIVE.value:
                count = db.query(User).filter(User.role == RoleEnum.ADMIN.value, User.status == AccountStatus.ACTIVE.value).count()
                if count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail={"error_code": "LAST_ADMIN_PROTECTED", "message": "Cannot demote or lock the last usable admin"}
                    )

        # OQ-05 (docs/41 R2): another admin must change an admin's own role or status
        if actor_id == user_id and ((role and role != user.role) or (user_status and user_status != user.status)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error_code": "SELF_MODIFICATION_FORBIDDEN", "message": "Ask another admin to change your own role or status"}
            )

        if role:
            if role not in [RoleEnum.ADMIN.value, RoleEnum.TEACHER.value, RoleEnum.STUDENT.value]:
                raise HTTPException(status_code=400, detail={"error_code": "INVALID_ROLE", "message": "Invalid role"})
            user.role = role
            log_admin_action(db, actor_id, "USER_ROLE_CHANGED", "USER", str(user_id))

        if user_status:
            if user_status not in [AccountStatus.ACTIVE.value, AccountStatus.LOCKED.value, AccountStatus.PENDING.value]:
                raise HTTPException(status_code=400, detail={"error_code": "INVALID_ACCOUNT_STATE", "message": "Invalid status"})
            user.status = user_status
            log_admin_action(db, actor_id, "USER_STATUS_CHANGED", "USER", str(user_id))
            if user_status != AccountStatus.ACTIVE.value:
                auth_repo.revoke_all_user_sessions(db, user_id)

        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        raise e
