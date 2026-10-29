"""Phase 17 — /health (liveness) and /ready (readiness), no auth (docs/43 D4)."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.services import health as health_svc

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request):
    checks = await run_in_threadpool(health_svc.readiness)
    if all(v == "ok" for v in checks.values()):
        return {"status": "ready", "checks": checks}
    return JSONResponse(status_code=503, content={
        "error_code": "NOT_READY", "message": "One or more dependencies are unavailable",
        "request_id": getattr(request.state, "request_id", ""), "checks": checks,
    })
