import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from app.models.trace import TraceEventType, SnapshotReason

class TraceEventCreate(BaseModel):
    sequence_number: int = Field(..., ge=1)
    event_type: TraceEventType
    client_timestamp: datetime
    payload: Dict[str, Any] = Field(default_factory=dict)

class TraceBatchRequest(BaseModel):
    events: List[TraceEventCreate] = Field(..., max_length=1000)

class TraceStateResponse(BaseModel):
    highest_contiguous_sequence: int
    next_expected_sequence: int
    # REQ-TRACE-013 (docs/39 D4): client-driven CHECKPOINT cadence
    checkpoint_interval_seconds: int = 60

class TraceBatchResponse(BaseModel):
    accepted_count: int
    state: TraceStateResponse

class TraceEventResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    sequence_number: int
    event_type: TraceEventType
    client_timestamp: datetime
    server_timestamp: datetime
    payload: Dict[str, Any]
    
    model_config = ConfigDict(from_attributes=True)

class TraceReplayResponse(BaseModel):
    items: List[TraceEventResponse]
    state: TraceStateResponse
    total: int
    skip: int
    limit: int

class SnapshotCreate(BaseModel):
    reason: SnapshotReason
    language: str
    source_code: str
    line_count: int

class SnapshotResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    reason: str
    language: str
    source_hash: str
    object_key: str
    line_count: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ScratchpadRequest(BaseModel):
    content: str = Field(..., max_length=50000, description="Scratchpad content (max 50KB)")
    client_timestamp: datetime

class ScratchpadRevisionResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    revision_sequence: int
    content: str
    client_timestamp: datetime
    server_timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ScratchpadHistoryResponse(BaseModel):
    items: List[ScratchpadRevisionResponse]
    total: int
