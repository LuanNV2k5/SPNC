"""Phase 10A — Test case schemas (REQ-PROB-002, docs/36)."""
import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TestCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_data: str = ""
    expected_output: str
    is_sample: bool = False
    score_weight: int = Field(default=10, ge=0)
    order_index: Optional[int] = Field(default=None, ge=1)


class TestCaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_data: Optional[str] = None
    expected_output: Optional[str] = None
    is_sample: Optional[bool] = None
    score_weight: Optional[int] = Field(default=None, ge=0)


class TestCaseResponse(BaseModel):
    """Owner TEACHER view: full data including hidden cases."""
    id: uuid.UUID
    problem_id: uuid.UUID
    order_index: int
    input_data: str
    expected_output: str
    is_sample: bool
    score_weight: int


class TestCaseListResponse(BaseModel):
    items: List[TestCaseResponse]
    total: int


class SampleCaseResponse(BaseModel):
    """Student view: sample cases only (is_sample = true)."""
    order_index: int
    input_data: str
    expected_output: str


class SampleCaseListResponse(BaseModel):
    items: List[SampleCaseResponse]
