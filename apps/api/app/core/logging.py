"""Phase 17 — Structured logs (docs/43 §3.4, §3.5).

One JSON object per line on stdout. `request_id` comes from a contextvar set by the HTTP
middleware; correlation ids (docs/07 §4.7) are passed as `extra={...}`. Secrets are masked
in the formatter as a safety net (PROJECT_RULES #25); code must still never log them.
"""
import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

CONTEXT_FIELDS = ("request_id", "session_id", "run_id", "submission_id", "exam_id", "execution_generation", "daemon")
ACCESS_FIELDS = ("method", "route", "status", "duration_ms")

_REDACTIONS = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    (re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^:/@\s]+):[^@\s]+@"), r"\1:[REDACTED]@"),
    (re.compile(r"(?i)\b(password|passwd|secret|secret_key|token|access_token|refresh_token|api_key)"
                r"(\"?'?\s*[:=]\s*\"?'?)([^\s\"',;&}]+)"), r"\1\2[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class _ContextFilter(logging.Filter):
    def __init__(self, daemon: Optional[str] = None):
        super().__init__()
        self.daemon = daemon

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            record.request_id = request_id_var.get()
        if self.daemon and getattr(record, "daemon", None) is None:
            record.daemon = self.daemon
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for field in CONTEXT_FIELDS + ACCESS_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value if isinstance(value, (int, float)) else redact(str(value))
        if record.exc_info:
            entry["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(daemon: Optional[str] = None, stream=None, fmt: Optional[str] = None) -> logging.Handler:
    """Replaces root handlers with one stdout handler (idempotent). LOG_FORMAT=text for local use."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(TextFormatter() if (fmt or settings.LOG_FORMAT).lower() == "text" else JsonFormatter())
    handler.addFilter(_ContextFilter(daemon))
    root = logging.getLogger()
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())
    return handler
