import uuid
from typing import List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.models.user import User, AuditLog, RoleEnum, AccountStatus
from app.models.class_org import Class, ClassMembership
from app.models.exam import Exam

LAST_USABLE_ADMIN_LOCK_KEY = 72946281

def acquire_last_admin_lock(db: Session):
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": LAST_USABLE_ADMIN_LOCK_KEY})


def get_users_paginated(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[User], int]:
    total = db.query(func.count(User.id)).scalar()
    users = db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return users, total

def get_classes_paginated(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[Class], int]:
    total = db.query(func.count(Class.id)).scalar()
    classes = db.query(Class).order_by(Class.created_at.desc()).offset(skip).limit(limit).all()
    return classes, total

def get_exams_paginated(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[Exam], int]:
    total = db.query(func.count(Exam.id)).scalar()
    exams = db.query(Exam).order_by(Exam.created_at.desc()).offset(skip).limit(limit).all()
    return exams, total

def get_audit_logs_paginated(db: Session, skip: int = 0, limit: int = 50) -> Tuple[List[AuditLog], int]:
    total = db.query(func.count(AuditLog.id)).scalar()
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return logs, total

def get_dashboard_summary(db: Session) -> dict:
    total_users = db.query(func.count(User.id)).scalar()
    admin_count = db.query(func.count(User.id)).filter(User.role == RoleEnum.ADMIN.value).scalar()
    teacher_count = db.query(func.count(User.id)).filter(User.role == RoleEnum.TEACHER.value).scalar()
    student_count = db.query(func.count(User.id)).filter(User.role == RoleEnum.STUDENT.value).scalar()

    active_count = db.query(func.count(User.id)).filter(User.status == AccountStatus.ACTIVE.value).scalar()
    locked_count = db.query(func.count(User.id)).filter(User.status == AccountStatus.LOCKED.value).scalar()

    total_classes = db.query(func.count(Class.id)).scalar()
    total_exams = db.query(func.count(Exam.id)).scalar()

    return {
        "total_users": total_users,
        "users_by_role": {"ADMIN": admin_count, "TEACHER": teacher_count, "STUDENT": student_count},
        "users_by_status": {"ACTIVE": active_count, "LOCKED": locked_count},
        "total_classes": total_classes,
        "total_exams": total_exams,
        "recent_audit_count": 0
    }

def get_active_admins_count(db: Session) -> int:
    return db.query(func.count(User.id)).filter(User.role == RoleEnum.ADMIN.value, User.status == AccountStatus.ACTIVE.value).scalar()
