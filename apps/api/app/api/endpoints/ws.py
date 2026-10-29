"""Phase 09C — Teacher notification WebSocket (docs/35 §4 09C).

Protocol:
  client -> {"type": "auth", "access_token": "..."}           (first message, within WS_AUTH_TIMEOUT_SECONDS)
  client -> {"type": "subscribe", "class_id": "..."} | {"type": "subscribe", "exam_id": "..."}
  server -> {"type": "authenticated"} | {"type": "subscribed", ...} | {"type": "error", "error_code": ...}
  server -> notifications: signal.created | run.completed | session.state (identifiers only)
The token travels in a message, never in the URL, so access logs cannot capture it.
"""
import asyncio
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.api.deps import resolve_user_from_token
from app.core import metrics
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import RoleEnum
from app.realtime.hub import Subscriber, hub, threadsafe_sender
from app.services import observation_auth as auth

router = APIRouter()

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403


def _authenticate(token: str):
    with SessionLocal() as db:
        user = resolve_user_from_token(db, token)
        role = getattr(user.role, "value", user.role)
        return user.id, role


def _authorize_subscription(teacher_id: uuid.UUID, class_id, exam_id):
    with SessionLocal() as db:
        from app.models.user import User
        teacher = db.get(User, teacher_id)
        if class_id is not None:
            auth.authorize_class(db, teacher, class_id)
        else:
            auth.authorize_exam(db, teacher, exam_id)


@router.websocket("/ws/teacher")
async def teacher_notifications(websocket: WebSocket):
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=settings.WS_AUTH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        metrics.WS_AUTH_REJECTIONS.labels(reason="no_auth_message").inc()
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return
    if not isinstance(first, dict) or first.get("type") != "auth" or not first.get("access_token"):
        metrics.WS_AUTH_REJECTIONS.labels(reason="no_auth_message").inc()
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return
    try:
        teacher_id, role = await run_in_threadpool(_authenticate, first["access_token"])
    except HTTPException:
        metrics.WS_AUTH_REJECTIONS.labels(reason="invalid_token").inc()
        await websocket.close(code=CLOSE_UNAUTHENTICATED)
        return
    if role != RoleEnum.TEACHER.value:
        metrics.WS_AUTH_REJECTIONS.labels(reason="forbidden_role").inc()
        await websocket.close(code=CLOSE_FORBIDDEN)
        return

    key = id(websocket)
    hub.register(key, Subscriber(teacher_id=teacher_id, send=threadsafe_sender(websocket, asyncio.get_running_loop())))
    metrics.WS_ACTIVE.inc()
    try:
        await websocket.send_json({"type": "authenticated"})
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict) or msg.get("type") != "subscribe":
                await websocket.send_json({"type": "error", "error_code": "WS_UNKNOWN_MESSAGE"})
                continue
            try:
                class_id = uuid.UUID(msg["class_id"]) if msg.get("class_id") else None
                exam_id = uuid.UUID(msg["exam_id"]) if msg.get("exam_id") else None
            except (ValueError, TypeError):
                class_id = exam_id = None
            if (class_id is None) == (exam_id is None):
                await websocket.send_json({"type": "error", "error_code": "WS_INVALID_SUBSCRIPTION"})
                continue
            try:
                await run_in_threadpool(_authorize_subscription, teacher_id, class_id, exam_id)
            except HTTPException as e:
                await websocket.send_json({"type": "error", "error_code": e.detail.get("error_code", "FORBIDDEN_RESOURCE")})
                continue
            if class_id:
                hub.add_class(key, class_id)
                await websocket.send_json({"type": "subscribed", "class_id": str(class_id)})
            else:
                hub.add_exam(key, exam_id)
                await websocket.send_json({"type": "subscribed", "exam_id": str(exam_id)})
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        hub.unregister(key)
        metrics.WS_ACTIVE.dec()
