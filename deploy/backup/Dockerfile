# Phase 18 — SPNC backup / restore tool (docs/44 §3.1).
# postgres:16-alpine so pg_dump / pg_restore match the server major version (PostgreSQL 16).
FROM postgres:16-alpine

RUN apk add --no-cache python3 py3-psycopg2 py3-pip \
 && pip install --no-cache-dir --break-system-packages minio==7.2.20 \
 && apk del py3-pip

COPY spnc_backup.py /usr/local/bin/spnc_backup.py

ENV BACKUP_DIR=/backups PYTHONUNBUFFERED=1
ENTRYPOINT ["python3", "/usr/local/bin/spnc_backup.py"]
CMD ["schedule"]
