import uuid
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

class AdminUserListResponse(BaseModel):
    items: List["AdminUserDetailResponse"]
    total: int
    page: int
    size: int

class AdminUserDetailResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    full_name: str
    role: str
    status: str
    force_password_change: bool
    created_at: datetime
    updated_at: datetime

class AdminUserCreateRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: str
    role: str

class AdminUserPatchRequest(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None

class AdminClassDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    academic_year: str
    owner_id: uuid.UUID
    is_active: bool
    created_at: datetime

class AdminClassListResponse(BaseModel):
    items: List[AdminClassDetailResponse]
    total: int
    page: int
    size: int

class AdminExamDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    owner_id: uuid.UUID
    status: str
    start_time: datetime
    end_time: datetime

class AdminExamListResponse(BaseModel):
    items: List[AdminExamDetailResponse]
    total: int
    page: int
    size: int

class AdminAuditLogResponse(BaseModel):
    id: uuid.UUID
    actor_id: Optional[uuid.UUID]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    timestamp: datetime
    request_id: Optional[str]

class AdminAuditLogListResponse(BaseModel):
    items: List[AdminAuditLogResponse]
    total: int
    page: int
    size: int

class AdminDashboardSummaryResponse(BaseModel):
    total_users: int
    users_by_role: dict
    users_by_status: dict
    total_classes: int
    total_exams: int
    recent_audit_count: int

class AdminSettingsPatchRequest(BaseModel):
    retention_days: Optional[int] = None
    idle_threshold_minutes: Optional[int] = None   # REQ-USER-007: 1-60, applies to new sessions

class AdminSettingsResponse(BaseModel):
    retention_days: int
    idle_threshold_minutes: int

AdminUserListResponse.model_rebuild()
