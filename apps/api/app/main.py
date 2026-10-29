from fastapi import FastAPI, Request

from fastapi.responses import JSONResponse

from fastapi.exceptions import RequestValidationError

from starlette.exceptions import HTTPException as StarletteHTTPException

import logging
import re
import time
import uuid



from app.core.config import settings
from app.core.logging import request_id_var
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.services.storage import StorageConflict, StorageUnavailable

from app.api.endpoints import auth



app = FastAPI(title=settings.PROJECT_NAME)



_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
access_logger = logging.getLogger("spnc.access")
error_logger = logging.getLogger("spnc.error")


def _route_template(scope) -> str:
    """Route template, never the raw path: ids must not become labels (docs/43 §4.2).
    Included routers keep their prefix outside the matched route, so the template is rebuilt
    from the request path with each path-parameter segment put back as {name}."""
    if scope.get("route") is None:
        return "unmatched"
    names = {str(v): k for k, v in (scope.get("path_params") or {}).items()}
    return "/".join(f"{{{names[s]}}}" if s in names else s for s in scope["path"].split("/"))


@app.middleware("http")

async def add_request_id(request: Request, call_next):
    # docs/43 F5: a client id is kept only when it is short and safe to log
    client_id = request.headers.get("X-Request-ID", "")
    request_id = client_id if _REQUEST_ID_RE.match(client_id) else str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            # docs/43 F6: logged once with traceback; the client never sees exception text
            error_logger.exception("Unhandled exception")
            response = JSONResponse(status_code=500, content={
                "error_code": "INTERNAL_ERROR", "message": "Internal server error", "request_id": request_id})
        response.headers["X-Request-ID"] = request_id
        route = _route_template(request.scope)
        elapsed = time.perf_counter() - started
        HTTP_REQUESTS.labels(method=request.method, route=route, status=str(response.status_code)).inc()
        HTTP_DURATION.labels(method=request.method, route=route).observe(elapsed)
        # No query string, headers or body (docs/43 §3.4)
        access_logger.info("request", extra={"method": request.method, "route": route,
                                             "status": response.status_code, "duration_ms": round(elapsed * 1000, 1)})
        return response
    finally:
        request_id_var.reset(token)



@app.exception_handler(StarletteHTTPException)

async def http_exception_handler(request: Request, exc: StarletteHTTPException):

    detail = exc.detail

    if isinstance(detail, str):

        detail = {"message": detail}

    if isinstance(detail, dict):

        if "error_code" not in detail:

            detail["error_code"] = "HTTP_ERROR"

        if "request_id" not in detail:

            detail["request_id"] = getattr(request.state, "request_id", "")

    # Keep headers such as Retry-After (429) and WWW-Authenticate (401)
    return JSONResponse(status_code=exc.status_code, content=detail, headers=getattr(exc, "headers", None))



@app.exception_handler(StorageUnavailable)
async def storage_unavailable_handler(request: Request, exc: StorageUnavailable):
    # docs/37 D6: transient and retryable; no metadata row is written (upload-first)
    return JSONResponse(status_code=503, content={
        "error_code": "STORAGE_UNAVAILABLE", "message": "Snapshot storage is unavailable, retry later",
        "request_id": getattr(request.state, "request_id", ""),
    })


@app.exception_handler(StorageConflict)
async def storage_conflict_handler(request: Request, exc: StorageConflict):
    return JSONResponse(status_code=409, content={
        "error_code": "SNAPSHOT_CONTENT_CONFLICT", "message": "A different snapshot already exists under this key",
        "request_id": getattr(request.state, "request_id", ""),
    })


@app.exception_handler(RequestValidationError)

async def validation_exception_handler(request: Request, exc: RequestValidationError):

    def _safe_errors(errors):
        safe = []
        for err in errors:
            safe_err = {}
            for k, v in err.items():
                if k == "ctx" and isinstance(v, dict):
                    # ctx may contain non-serializable objects (e.g. ValueError in Python 3.14)
                    safe_err[k] = {ck: str(cv) for ck, cv in v.items()}
                elif isinstance(v, Exception):
                    safe_err[k] = str(v)
                else:
                    safe_err[k] = v
            safe.append(safe_err)
        return safe

    return JSONResponse(

        status_code=422,

        content={

            "error_code": "VALIDATION_ERROR",

            "message": "Request validation failed",

            "details": _safe_errors(exc.errors()),

            "request_id": getattr(request.state, "request_id", "")

        }

    )



from app.api.endpoints import auth, admin, academic, trace, run, observation, annotation, ws, testcase, submission, exam_lifecycle, statistics, points, health

app.include_router(health.router, tags=["health"])   # docs/43 D4: root path, no auth
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
app.include_router(academic.router, prefix=f"{settings.API_V1_STR}", tags=["academic"])
app.include_router(trace.router, prefix=f"{settings.API_V1_STR}", tags=["trace"])
app.include_router(run.router, prefix=f"{settings.API_V1_STR}/my/coding-sessions", tags=["run"])
app.include_router(observation.router, prefix=f"{settings.API_V1_STR}", tags=["observation"])
app.include_router(annotation.router, prefix=f"{settings.API_V1_STR}")
app.include_router(ws.router, prefix=f"{settings.API_V1_STR}")
app.include_router(testcase.router, prefix=f"{settings.API_V1_STR}", tags=["test-cases"])
app.include_router(submission.router, prefix=f"{settings.API_V1_STR}", tags=["submissions"])
app.include_router(exam_lifecycle.router, prefix=f"{settings.API_V1_STR}")
app.include_router(statistics.router, prefix=f"{settings.API_V1_STR}")
app.include_router(points.router, prefix=f"{settings.API_V1_STR}")
