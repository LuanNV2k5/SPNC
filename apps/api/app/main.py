from fastapi import FastAPI, Request

from fastapi.responses import JSONResponse

from fastapi.exceptions import RequestValidationError

from starlette.exceptions import HTTPException as StarletteHTTPException

import uuid



from app.core.config import settings

from app.api.endpoints import auth



app = FastAPI(title=settings.PROJECT_NAME)



@app.middleware("http")

async def add_request_id(request: Request, call_next):

    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    request.state.request_id = request_id

    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id

    return response



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

    return JSONResponse(status_code=exc.status_code, content=detail)



@app.exception_handler(RequestValidationError)

async def validation_exception_handler(request: Request, exc: RequestValidationError):

    return JSONResponse(

        status_code=422,

        content={

            "error_code": "VALIDATION_ERROR",

            "message": "Request validation failed",

            "details": exc.errors(),

            "request_id": getattr(request.state, "request_id", "")

        }

    )



from app.api.endpoints import auth, admin

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(admin.router, prefix=f"{settings.API_V1_STR}/admin", tags=["admin"])
