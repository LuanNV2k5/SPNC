import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import require_admin, get_current_user
from app.models.user import User
from app.models.class_org import Class
from app.models.exam import Exam, ExamStatus
from app.schemas.admin import (
    AdminUserListResponse, AdminUserDetailResponse, AdminUserCreateRequest, AdminUserPatchRequest,
    AdminClassListResponse, AdminClassDetailResponse, AdminExamListResponse, AdminExamDetailResponse,
    AdminAuditLogListResponse, AdminDashboardSummaryResponse, AdminSettingsPatchRequest, AdminSettingsResponse
)
from app.repositories import admin as admin_repo
from app.services import admin as admin_service
from app.services import exam_lifecycle, system_settings
from app.models.user import SystemSetting

router = APIRouter(dependencies=[Depends(require_admin)])

@router.get("/users", response_model=AdminUserListResponse)
def list_users(page: int = 1, size: int = 50, db: Session = Depends(get_db)):
    size = min(max(size, 1), 100)
    page = max(page, 1)
    users, total = admin_repo.get_users_paginated(db, skip=(page - 1) * size, limit=size)
    return {"items": users, "total": total, "page": page, "size": size}

@router.post("/users", response_model=AdminUserDetailResponse)
def create_user(request: AdminUserCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = admin_service.create_user(
        db, current_user.id, request.username, request.email, request.password, request.full_name, request.role
    )
    return user

@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail={"error_code": "USER_NOT_FOUND", "message": "User not found"})
    return user

@router.patch("/users/{user_id}", response_model=AdminUserDetailResponse)
def update_user(user_id: uuid.UUID, request: AdminUserPatchRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return admin_service.update_user(db, current_user.id, user_id, request.role, request.status)

@router.get("/classes", response_model=AdminClassListResponse)
def list_classes(page: int = 1, size: int = 50, db: Session = Depends(get_db)):
    size = min(size, 100)
    classes, total = admin_repo.get_classes_paginated(db, skip=(page - 1) * size, limit=size)
    return {"items": classes, "total": total, "page": page, "size": size}

@router.get("/classes/{class_id}", response_model=AdminClassDetailResponse)
def get_class(class_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Class).filter(Class.id == class_id).first()
    if not c:
        raise HTTPException(status_code=404, detail={"error_code": "CLASS_NOT_FOUND", "message": "Class not found"})
    return c

@router.get("/exams", response_model=AdminExamListResponse)
def list_exams(page: int = 1, size: int = 50, db: Session = Depends(get_db)):
    size = min(size, 100)
    exams, total = admin_repo.get_exams_paginated(db, skip=(page - 1) * size, limit=size)
    return {"items": exams, "total": total, "page": page, "size": size}

@router.get("/exams/{exam_id}", response_model=AdminExamDetailResponse)
def get_exam(exam_id: uuid.UUID, db: Session = Depends(get_db)):
    e = db.query(Exam).filter(Exam.id == exam_id).first()
    if not e:
        raise HTTPException(status_code=404, detail={"error_code": "EXAM_NOT_FOUND", "message": "Exam not found"})
    return e

@router.patch("/exams/{exam_id}/cancel")
def cancel_exam(exam_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # docs/36 D13: DRAFT/SCHEDULED only until OQ-23 is decided
    exam_lifecycle.admin_cancel_exam(db, current_user, exam_id)
    db.commit()
    return {"message": "Exam cancelled"}

@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def list_audit_logs(page: int = 1, size: int = 50, db: Session = Depends(get_db)):
    size = min(size, 100)
    logs, total = admin_repo.get_audit_logs_paginated(db, skip=(page - 1) * size, limit=size)
    return {"items": logs, "total": total, "page": page, "size": size}

@router.get("/dashboard/summary", response_model=AdminDashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    return admin_repo.get_dashboard_summary(db)

@router.get("/settings", response_model=AdminSettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    return system_settings.read_settings(db)

@router.patch("/settings")
def update_settings(req: AdminSettingsPatchRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = system_settings.update_settings(db, current_user, req.retention_days, req.idle_threshold_minutes)
    db.commit()
    return {"message": "success", **result}
