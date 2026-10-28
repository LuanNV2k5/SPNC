"""Phase 09C — Teacher notification hub (docs/35 §4 09C, D4; NFR-REALTIME-001..003).

PostgreSQL triggers emit id-only NOTIFY payloads on commit. One listener thread per API
process LISTENs, resolves which subscribed teachers may see each event (docs/35 §3 rule),
and pushes the message to their WebSockets. Delivery is best-effort: the database stays the
source of truth and clients resync over REST after reconnecting.
"""
import asyncio
import json
import logging
import select
import threading
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import psycopg2
from sqlalchemy import and_, exists, select as sa_select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.class_org import Class, ClassMembership
from app.models.exam import ExamAssignment, ExamParticipation
from app.models.session import CodingSession
from app.services.observation_auth import session_visible_in_class_clause

logger = logging.getLogger(__name__)

CHANNEL = "spnc_observation"
# Only these keys ever leave the server (NFR-REALTIME-002: no source code, no evidence)
ALLOWED_KEYS = {
    "signal.created": ("signal_id", "session_id", "student_id", "signal_type"),
    "run.completed": ("run_id", "session_id", "student_id", "verdict", "status"),
    "session.state": ("session_id", "student_id", "status"),
    "submission.judged": ("submission_id", "session_id", "student_id", "verdict"),
}


@dataclass
class Subscriber:
    teacher_id: uuid.UUID
    send: callable  # thread-safe send(message: dict)
    class_ids: Set[uuid.UUID] = field(default_factory=set)
    exam_ids: Set[uuid.UUID] = field(default_factory=set)


class NotificationHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: Dict[int, Subscriber] = {}
        self._listener: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._listening = threading.Event()

    # -- subscription registry -------------------------------------------------
    def register(self, key: int, subscriber: Subscriber) -> None:
        with self._lock:
            self._subscribers[key] = subscriber
        self.ensure_listener()

    def unregister(self, key: int) -> None:
        with self._lock:
            self._subscribers.pop(key, None)

    def add_class(self, key: int, class_id: uuid.UUID) -> None:
        with self._lock:
            self._subscribers[key].class_ids.add(class_id)

    def add_exam(self, key: int, exam_id: uuid.UUID) -> None:
        with self._lock:
            self._subscribers[key].exam_ids.add(exam_id)

    def _snapshot(self) -> List[Subscriber]:
        with self._lock:
            return [Subscriber(s.teacher_id, s.send, set(s.class_ids), set(s.exam_ids)) for s in self._subscribers.values()]

    # -- listener ---------------------------------------------------------------
    def ensure_listener(self) -> None:
        with self._lock:
            if self._listener and self._listener.is_alive():
                return
            self._stop.clear()
            self._listener = threading.Thread(target=self._listen, name="spnc-notify-listener", daemon=True)
            self._listener.start()

    def stop(self) -> None:
        self._stop.set()

    def wait_until_listening(self, timeout: float = 5.0) -> bool:
        return self._listening.wait(timeout)

    def _listen(self) -> None:
        while not self._stop.is_set():
            conn = None
            try:
                conn = psycopg2.connect(settings.DATABASE_URL)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                with conn.cursor() as cur:
                    cur.execute(f"LISTEN {CHANNEL};")
                self._listening.set()
                while not self._stop.is_set():
                    if select.select([conn], [], [], 1.0) == ([], [], []):
                        continue
                    conn.poll()
                    while conn.notifies:
                        self._handle(conn.notifies.pop(0).payload)
            except Exception as e:
                # Never log payloads or credentials; reconnect after a short pause
                logger.error(f"Notification listener error: {type(e).__name__}")
                self._stop.wait(2.0)
            finally:
                self._listening.clear()
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def _handle(self, payload: str) -> None:
        try:
            event = json.loads(payload)
        except ValueError:
            return
        event_type = event.get("type")
        if event_type not in ALLOWED_KEYS:
            return
        message = {"type": event_type, **{k: event.get(k) for k in ALLOWED_KEYS[event_type]}}
        subscribers = self._snapshot()
        if not subscribers or not event.get("session_id"):
            return
        session_id = uuid.UUID(event["session_id"])
        with SessionLocal() as db:
            for sub in subscribers:
                if self._visible(db, sub, session_id):
                    sub.send(message)

    @staticmethod
    def _visible(db, sub: Subscriber, session_id: uuid.UUID) -> bool:
        """docs/35 §3: class subscription -> session visible in that class; exam subscription -> exam session of an observed student."""
        for class_id in sub.class_ids:
            if db.scalar(sa_select(exists(
                sa_select(CodingSession.id)
                .join(ClassMembership, and_(ClassMembership.student_id == CodingSession.student_id,
                                            ClassMembership.class_id == class_id,
                                            ClassMembership.is_active == True))
                .join(Class, and_(Class.id == class_id, Class.owner_id == sub.teacher_id))
                .where(and_(CodingSession.id == session_id, session_visible_in_class_clause(class_id, sub.teacher_id)))
            ))):
                return True
        for exam_id in sub.exam_ids:
            if db.scalar(sa_select(exists(
                sa_select(CodingSession.id)
                .join(ExamParticipation, ExamParticipation.id == CodingSession.exam_participation_id)
                .join(ExamAssignment, ExamAssignment.exam_id == ExamParticipation.exam_id)
                .join(Class, and_(Class.id == ExamAssignment.class_id, Class.owner_id == sub.teacher_id))
                .join(ClassMembership, and_(ClassMembership.class_id == Class.id,
                                            ClassMembership.student_id == CodingSession.student_id,
                                            ClassMembership.is_active == True))
                .where(and_(CodingSession.id == session_id, ExamParticipation.exam_id == exam_id))
            ))):
                return True
        return False


hub = NotificationHub()


def threadsafe_sender(websocket, loop: asyncio.AbstractEventLoop):
    """Builds a send(message) callable usable from the listener thread."""
    def send(message: dict) -> None:
        try:
            asyncio.run_coroutine_threadsafe(websocket.send_json(message), loop)
        except RuntimeError:
            pass  # loop closed: the socket is gone; the client resyncs over REST
    return send
