from typing import Optional, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models.run_submit import RunStatus, RunVerdict

class RunCreate(BaseModel):
    snapshot_id: UUID = Field(..., description="The ID of the immutable snapshot to execute.")
    input: Optional[str] = Field(None, description="Standard input to provide to the executed code.")

class RunResponse(BaseModel):
    id: UUID
    session_id: UUID
    snapshot_id: UUID
    status: RunStatus
    verdict: Optional[RunVerdict] = None
    execution_time_ms: Optional[int] = None
    execution_memory_kb: Optional[int] = None
    testcase_results: Optional[Any] = None
    execution_generation: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
