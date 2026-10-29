# Phase 11 — SPNC API / worker / scheduler image (docs/37 §3.3)
FROM python:3.14.4-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Unprivileged by default; the demo judge worker overrides this (docs/37 D3)
RUN useradd --uid 10001 --create-home spnc
USER spnc

EXPOSE 8000
# docs/43 §3.2: JSON logs + internal metrics port 9100 (not published), then uvicorn
CMD ["python", "-m", "app.serve"]
