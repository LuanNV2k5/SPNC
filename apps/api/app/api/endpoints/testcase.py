"""Phase 10A — Test case endpoints (REQ-PROB-002). Thin router."""
import uuid

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_teacher
from app.db.session import get_db
from app.models.user import User
from app.schemas.testcase import (
    SampleCaseListResponse, TestCaseCreate, TestCaseListResponse, TestCaseResponse, TestCaseUpdate,
)
from app.services import testcase as svc

router = APIRouter()


@router.get("/problems/{problem_id}/test-cases", response_model=TestCaseListResponse,
            summary="[P10-T01] List test cases incl. hidden (owner Teacher)")
def list_test_cases(problem_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                    current_user: User = Depends(require_teacher)):
    items = svc.list_test_cases(db, current_user, problem_id)
    return {"items": items, "total": len(items)}


@router.post("/problems/{problem_id}/test-cases", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED,
             summary="[P10-T02] Add test case (owner Teacher)")
def create_test_case(req: TestCaseCreate, problem_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                     current_user: User = Depends(require_teacher)):
    return svc.create_test_case(db, current_user, problem_id, req)


@router.patch("/problems/{problem_id}/test-cases/{test_case_id}", response_model=TestCaseResponse,
              summary="[P10-T03] Update test case (owner Teacher)")
def update_test_case(req: TestCaseUpdate, problem_id: uuid.UUID = Path(...), test_case_id: uuid.UUID = Path(...),
                     db: Session = Depends(get_db), current_user: User = Depends(require_teacher)):
    return svc.update_test_case(db, current_user, problem_id, test_case_id, req)


@router.delete("/problems/{problem_id}/test-cases/{test_case_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="[P10-T04] Delete test case (owner Teacher)")
def delete_test_case(problem_id: uuid.UUID = Path(...), test_case_id: uuid.UUID = Path(...),
                     db: Session = Depends(get_db), current_user: User = Depends(require_teacher)):
    svc.delete_test_case(db, current_user, problem_id, test_case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/problems/{problem_id}/samples", response_model=SampleCaseListResponse,
            summary="[P10-T05] Sample test cases visible to anyone who can view the problem")
def list_samples(problem_id: uuid.UUID = Path(...), db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    return {"items": svc.list_samples(db, current_user, problem_id)}
