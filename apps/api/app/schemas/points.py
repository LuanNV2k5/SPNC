"""Phase 14A — Points schemas (no ranking fields)."""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PointTransactionItem(BaseModel):
    amount: int
    reason: str
    problem_id: Optional[uuid.UUID] = None
    problem_title: Optional[str] = None
    submission_id: Optional[uuid.UUID] = None
    created_at: datetime


class PointsSummary(BaseModel):
    student_id: uuid.UUID
    total: int
    transactions: List[PointTransactionItem]
