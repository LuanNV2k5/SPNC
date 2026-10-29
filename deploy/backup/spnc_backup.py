"""SPNC backup / restore tool (Phase 18, docs/44).

A backup set is one self-contained directory (docs/44 D5):

    spnc-<UTC timestamp>/
        db.dump         pg_dump --format=custom, taken from an exported snapshot
        blobs/<key>     every snapshot blob referenced by that snapshot
        manifest.json   revision, row counts, SHA-256 of the dump and of every blob

Consistency (docs/44 D3): the object keys, the row counts and the dump all come from one
REPEATABLE READ snapshot. Blobs are immutable and written before their row (upload-first),
so every key in the snapshot is in MinIO when the copy starts; a missing one fails the backup.

    spnc_backup.py backup                 create, verify and prune
    spnc_backup.py list
    spnc_backup.py verify-set <set>       offline check of a set
    spnc_backup.py restore <set>          into an empty database and bucket only
    spnc_backup.py verify-live            every object_key of the live database is readable
    spnc_backup.py schedule               daily loop at BACKUP_TIME_UTC (compose service)

Configuration comes from the environment (same names as the API: DATABASE_URL, S3_*).
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.parse import unquote, urlsplit

import psycopg2
from psycopg2 import sql

logger = logging.getLogger("spnc_backup")

SET_PREFIX = "spnc-"
SET_RE = re.compile(r"^spnc-\d{8}T\d{6}Z$")
PARTIAL_SUFFIX = ".partial"
MANIFEST_FORMAT = 1
CHUNK = 1024 * 1024


class BackupError(Exception):
    """The operation failed; nothing usable was produced (or the target was left untouched)."""


@dataclass
class Config:
    database_url: str
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "spnc-snapshots"
    s3_secure: bool = False
    backup_dir: str = "/backups"
    keep: int = 14
    time_utc: str = "19:00"
    # pg_dump / pg_restore are run as pg_cmd_prefix + [tool, ...]; tests use a `docker run` prefix
    pg_cmd_prefix: List[str] = field(default_factory=list)
    # Host the pg tools connect to, when it differs from DATABASE_URL's (tests: host.docker.internal)
    pg_tools_host: Optional[str] = None
    connect_timeout_seconds: int = 60

    @classmethod
    def from_env(cls, env=os.environ) -> "Config":
        return cls(
            database_url=env["DATABASE_URL"],
            s3_endpoint=env["S3_ENDPOINT"],
            s3_access_key=env["S3_ACCESS_KEY"],
            s3_secret_key=env["S3_SECRET_KEY"],
            s3_bucket=env.get("S3_BUCKET", "spnc-snapshots"),
            s3_secure=env.get("S3_SECURE", "false").lower() == "true",
            backup_dir=env.get("BACKUP_DIR", "/backups"),
            keep=int(env.get("BACKUP_KEEP", "14")),
            time_utc=env.get("BACKUP_TIME_UTC", "19:00"),
        )


# -- connections -----------------------------------------------------------------
def _plain_url(url: str) -> str:
    # SQLAlchemy-style "postgresql+psycopg2://" is not a libpq URL
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _pg_env(cfg: Config) -> Dict[str, str]:
    """libpq variables for pg_dump / pg_restore, so the password is not on a command line."""
    u = urlsplit(_plain_url(cfg.database_url))
    env = {
        "PGHOST": cfg.pg_tools_host or u.hostname or "localhost",
        "PGPORT": str(u.port or 5432),
        "PGUSER": unquote(u.username or ""),
        "PGPASSWORD": unquote(u.password or ""),
        "PGDATABASE": u.path.lstrip("/"),
    }
    return env


def _connect(cfg: Config):
    deadline = time.monotonic() + cfg.connect_timeout_seconds
    while True:
        try:
            return psycopg2.connect(_plain_url(cfg.database_url), connect_timeout=5)
        except psycopg2.OperationalError as e:
            if time.monotonic() > deadline:
                raise BackupError(f"PostgreSQL unreachable: {e}") from e
            time.sleep(2)


def _s3(cfg: Config):
    from minio import Minio
    return Minio(cfg.s3_endpoint, access_key=cfg.s3_access_key, secret_key=cfg.s3_secret_key, secure=cfg.s3_secure)


def _wait_s3(cfg: Config):
    client = _s3(cfg)
    deadline = time.monotonic() + cfg.connect_timeout_seconds
    while True:
        try:
            client.bucket_exists(cfg.s3_bucket)
            return client
        except Exception as e:
            if time.monotonic() > deadline:
                raise BackupError(f"MinIO unreachable: {e}") from e
            time.sleep(2)


def _run_pg_tool(cfg: Config, args: List[str], stdin=None, stdout=None):
    cmd = list(cfg.pg_cmd_prefix) + args
    env = dict(os.environ)
    env.update(_pg_env(cfg))
    proc = subprocess.run(cmd, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, env=env)
    if proc.returncode != 0:
        raise BackupError(f"{args[0]} failed ({proc.returncode}): {proc.stderr.decode(errors='replace').strip()}")


# -- helpers ---------------------------------------------------------------------
def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_blob_path(root: str, key: str) -> str:
    """Path of a key inside blobs/; refuses keys that would escape it (keys come from the database)."""
    parts = key.split("/")
    if not key or key.startswith("/") or "\\" in key or any(p in ("", ".", "..") for p in parts):
        raise BackupError(f"Unsafe object key: {key!r}")
    return os.path.join(root, "blobs", *parts)


def _public_tables(cur) -> List[str]:
    cur.execute("SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name")
    return [r[0] for r in cur.fetchall()]


def _row_counts(cur) -> Dict[str, int]:
    counts = {}
    for t in _public_tables(cur):
        cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t)))
        counts[t] = cur.fetchone()[0]
    return counts


def _referenced_keys(cur) -> Dict[str, str]:
    """object_key -> source_hash. Rows sharing a key must agree on the hash."""
    cur.execute("SELECT DISTINCT object_key, source_hash FROM code_snapshots ORDER BY object_key")
    keys: Dict[str, str] = {}
    for key, source_hash in cur.fetchall():
        if keys.setdefault(key, source_hash) != source_hash:
            raise BackupError(f"Rows referencing {key} disagree on source_hash")
    return keys


def _alembic_revision(cur) -> str:
    cur.execute("SELECT version_num FROM alembic_version")
    return cur.fetchone()[0]


def list_sets(backup_dir: str) -> List[str]:
    if not os.path.isdir(backup_dir):
        return []
    return sorted(d for d in os.listdir(backup_dir) if SET_RE.match(d) and os.path.isdir(os.path.join(backup_dir, d)))


# -- backup ----------------------------------------------------------------------
def create_backup(cfg: Config, now: Optional[datetime] = None) -> str:
    """Creates and verifies one set; returns its path. On failure no final set exists."""
    now = now or datetime.now(timezone.utc)
    os.makedirs(cfg.backup_dir, mode=0o700, exist_ok=True)
    for d in os.listdir(cfg.backup_dir):
        if d.endswith(PARTIAL_SUFFIX):
            logger.warning(f"Removing incomplete set {d}")
            shutil.rmtree(os.path.join(cfg.backup_dir, d), ignore_errors=True)

    name = SET_PREFIX + now.strftime("%Y%m%dT%H%M%SZ")
    final = os.path.join(cfg.backup_dir, name)
    if os.path.exists(final):
        raise BackupError(f"Set {name} already exists")
    staging = final + PARTIAL_SUFFIX
    os.makedirs(staging, mode=0o700)
    try:
        manifest = _write_set(cfg, staging, now)
        problems = verify_set(staging)
        if problems:
            raise BackupError("New set failed verification: " + "; ".join(problems[:5]))
        os.rename(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    logger.info(f"Backup {name}: {sum(manifest['row_counts'].values())} rows in "
                f"{len(manifest['row_counts'])} tables, {len(manifest['blobs'])} blobs")
    return final


def _write_set(cfg: Config, staging: str, now: datetime) -> dict:
    client = _wait_s3(cfg)
    conn = _connect(cfg)
    try:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_export_snapshot(), current_setting('server_version')")
            snapshot_id, server_version = cur.fetchone()
            revision = _alembic_revision(cur)
            counts = _row_counts(cur)
            keys = _referenced_keys(cur)
            # The exporting transaction stays open while pg_dump uses its snapshot
            dump_path = os.path.join(staging, "db.dump")
            with open(dump_path, "wb") as out:
                _run_pg_tool(cfg, ["pg_dump", "--format=custom", f"--snapshot={snapshot_id}"], stdout=out)
        conn.rollback()
    finally:
        conn.close()

    blobs = []
    missing = []
    for key, source_hash in keys.items():
        path = _safe_blob_path(staging, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            client.fget_object(cfg.s3_bucket, key, path)
        except Exception as e:
            if getattr(e, "code", None) in ("NoSuchKey", "NoSuchObject", "ResourceNotFound", "NoSuchBucket"):
                missing.append(key)
                continue
            raise BackupError(f"Cannot read {key}: {e}") from e
        digest = _sha256_file(path)
        if digest != source_hash:
            raise BackupError(f"Blob {key} does not match its source_hash")
        blobs.append({"key": key, "sha256": digest, "size": os.path.getsize(path)})
    if missing:
        raise BackupError(f"{len(missing)} referenced blob(s) missing from bucket {cfg.s3_bucket}: {missing[:5]}")

    manifest = {
        "format": MANIFEST_FORMAT,
        "created_at": now.isoformat(),
        "alembic_revision": revision,
        "server_version": server_version,
        "bucket": cfg.s3_bucket,
        "db_dump": {"file": "db.dump", "sha256": _sha256_file(dump_path), "size": os.path.getsize(dump_path)},
        "row_counts": counts,
        "blobs": blobs,
    }
    with open(os.path.join(staging, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


def prune(cfg: Config) -> List[str]:
    """Deletes all but the newest `keep` sets; returns the deleted names."""
    sets = list_sets(cfg.backup_dir)
    doomed = sets[:-cfg.keep] if cfg.keep > 0 else []
    for name in doomed:
        shutil.rmtree(os.path.join(cfg.backup_dir, name))
        logger.info(f"Pruned {name}")
    return doomed


def load_manifest(set_path: str) -> dict:
    try:
        with open(os.path.join(set_path, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise BackupError(f"Unreadable manifest in {set_path}: {e}") from e


def verify_set(set_path: str) -> List[str]:
    """Offline check; returns a list of problems (empty = the set is complete and intact)."""
    try:
        manifest = load_manifest(set_path)
    except BackupError as e:
        return [str(e)]
    problems = []
    if manifest.get("format") != MANIFEST_FORMAT:
        problems.append(f"Unknown manifest format {manifest.get('format')}")
    dump = os.path.join(set_path, manifest["db_dump"]["file"])
    if not os.path.isfile(dump):
        problems.append("db.dump missing")
    elif _sha256_file(dump) != manifest["db_dump"]["sha256"]:
        problems.append("db.dump checksum mismatch")
    for blob in manifest["blobs"]:
        try:
            path = _safe_blob_path(set_path, blob["key"])
        except BackupError as e:
            problems.append(str(e))
            continue
        if not os.path.isfile(path):
            problems.append(f"blob missing: {blob['key']}")
        elif _sha256_file(path) != blob["sha256"]:
            problems.append(f"blob checksum mismatch: {blob['key']}")
    return problems


# -- restore ---------------------------------------------------------------------
def restore(cfg: Config, set_path: str) -> dict:
    """Restores a set into an empty database and bucket, then verifies it (docs/44 §3.3)."""
    problems = verify_set(set_path)
    if problems:
        raise BackupError("Set failed verification, nothing restored: " + "; ".join(problems[:5]))
    manifest = load_manifest(set_path)

    client = _wait_s3(cfg)
    conn = _connect(cfg)
    try:
        with conn.cursor() as cur:
            tables = _public_tables(cur)
        conn.rollback()
    finally:
        conn.close()
    if tables:
        raise BackupError(f"Target database is not empty ({len(tables)} tables); restore needs a fresh database")
    if client.bucket_exists(cfg.s3_bucket):
        if next(iter(client.list_objects(cfg.s3_bucket, recursive=True)), None) is not None:
            raise BackupError(f"Target bucket {cfg.s3_bucket} is not empty")
    else:
        client.make_bucket(cfg.s3_bucket)

    # Blobs first, then rows: upload-first holds during the restore too
    for blob in manifest["blobs"]:
        client.fput_object(cfg.s3_bucket, blob["key"], _safe_blob_path(set_path, blob["key"]),
                           content_type="text/plain; charset=utf-8", metadata={"sha256": blob["sha256"]})
    with open(os.path.join(set_path, manifest["db_dump"]["file"]), "rb") as dump:
        _run_pg_tool(cfg, ["pg_restore", "--exit-on-error", "--single-transaction", "--no-owner",
                           "--no-privileges", f"--dbname={_pg_env(cfg)['PGDATABASE']}"], stdin=dump)

    problems = verify_restored(cfg, manifest)
    if problems:
        raise BackupError("Restored data does not match the set: " + "; ".join(problems[:5]))
    logger.info(f"Restored {os.path.basename(set_path)}: revision {manifest['alembic_revision']}, "
                f"{sum(manifest['row_counts'].values())} rows, {len(manifest['blobs'])} blobs")
    return manifest


def verify_restored(cfg: Config, manifest: dict) -> List[str]:
    problems = []
    conn = _connect(cfg)
    try:
        with conn.cursor() as cur:
            revision = _alembic_revision(cur)
            counts = _row_counts(cur)
        conn.rollback()
    finally:
        conn.close()
    if revision != manifest["alembic_revision"]:
        problems.append(f"alembic revision {revision} != {manifest['alembic_revision']}")
    if counts != manifest["row_counts"]:
        diff = sorted(t for t in set(counts) | set(manifest["row_counts"]) if counts.get(t) != manifest["row_counts"].get(t))
        problems.append(f"row counts differ for: {diff}")
    problems.extend(verify_live(cfg))
    return problems


def verify_live(cfg: Config) -> List[str]:
    """Every object_key in the database is in the bucket and its content matches source_hash."""
    client = _wait_s3(cfg)
    conn = _connect(cfg)
    try:
        with conn.cursor() as cur:
            keys = _referenced_keys(cur)
        conn.rollback()
    finally:
        conn.close()
    problems = []
    for key, source_hash in keys.items():
        response = None
        try:
            response = client.get_object(cfg.s3_bucket, key)
            h = hashlib.sha256()
            for chunk in response.stream(CHUNK):
                h.update(chunk)
            if h.hexdigest() != source_hash:
                problems.append(f"content mismatch: {key}")
        except Exception as e:
            problems.append(f"unreadable: {key} ({getattr(e, 'code', e)})")
        finally:
            if response is not None:
                response.close()
                response.release_conn()
    return problems


# -- schedule --------------------------------------------------------------------
def next_run(now: datetime, time_utc: str) -> datetime:
    hour, minute = (int(x) for x in time_utc.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def _write_status(cfg: Config, status: dict):
    try:
        with open(os.path.join(cfg.backup_dir, "last-backup.json"), "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
    except OSError as e:
        logger.warning(f"Cannot write status file: {e}")


def run_scheduled_backup(cfg: Config) -> bool:
    started = datetime.now(timezone.utc)
    try:
        path = create_backup(cfg, now=started)
        pruned = prune(cfg)
        _write_status(cfg, {"status": "ok", "set": os.path.basename(path), "pruned": pruned,
                            "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat()})
        return True
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        _write_status(cfg, {"status": "failed", "error": str(e), "started_at": started.isoformat(),
                            "finished_at": datetime.now(timezone.utc).isoformat()})
        return False


def schedule(cfg: Config):
    next_run(datetime.now(timezone.utc), cfg.time_utc)   # fail fast on a bad BACKUP_TIME_UTC
    logger.info(f"Backup schedule: daily at {cfg.time_utc} UTC into {cfg.backup_dir}, keep {cfg.keep}")
    while True:
        at = next_run(datetime.now(timezone.utc), cfg.time_utc)
        logger.info(f"Next backup at {at.isoformat()}")
        while (remaining := (at - datetime.now(timezone.utc)).total_seconds()) > 0:
            time.sleep(min(remaining, 60))
        run_scheduled_backup(cfg)


# -- CLI -------------------------------------------------------------------------
def _set_path(name: str) -> str:
    return name if os.path.isdir(name) else os.path.join(os.environ.get("BACKUP_DIR", "/backups"), name)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="spnc_backup")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup")
    sub.add_parser("list")
    sub.add_parser("verify-live")
    sub.add_parser("schedule")
    for name in ("verify-set", "restore"):
        p = sub.add_parser(name)
        p.add_argument("set", help="set directory or name inside BACKUP_DIR")
    args = parser.parse_args(argv)

    if args.command == "verify-set":
        problems = verify_set(_set_path(args.set))
        for p in problems:
            print(p)
        print("OK" if not problems else f"FAILED ({len(problems)} problems)")
        return 0 if not problems else 1
    if args.command == "list":
        for name in list_sets(os.environ.get("BACKUP_DIR", "/backups")):
            print(name)
        return 0

    cfg = Config.from_env()
    try:
        if args.command == "backup":
            return 0 if run_scheduled_backup(cfg) else 1
        if args.command == "restore":
            restore(cfg, _set_path(args.set))
            print("RESTORE OK")
            return 0
        if args.command == "verify-live":
            problems = verify_live(cfg)
            for p in problems:
                print(p)
            print("OK" if not problems else f"FAILED ({len(problems)} problems)")
            return 0 if not problems else 1
        if args.command == "schedule":
            schedule(cfg)
    except BackupError as e:
        logger.error(str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
