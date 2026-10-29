"""Phase 11 — Operator CLI (docs/37 §3.2).

    SPNC_BOOTSTRAP_ADMIN_PASSWORD=... python -m app.cli create-admin --username admin --email admin@example.org
    python -m app.cli retention-purge [--apply] [--max-batches N]     (docs/45; dry run by default)
"""
import argparse
import json
import os
import sys

from app.db.session import SessionLocal
from app.services.bootstrap import BootstrapRefused, create_first_admin
from app.services.retention import purge as retention_purge

PASSWORD_ENV = "SPNC_BOOTSTRAP_ADMIN_PASSWORD"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help=f"Create the first ADMIN (password from ${PASSWORD_ENV})")
    create.add_argument("--username", required=True)
    create.add_argument("--email", required=True)
    create.add_argument("--full-name", default="Administrator")
    purge = sub.add_parser("retention-purge", help="Purge raw trace past retention (dry run unless --apply)")
    purge.add_argument("--apply", action="store_true", help="Delete; without it only counts are reported")
    purge.add_argument("--max-batches", type=int, default=None)
    args = parser.parse_args(argv)

    if args.command == "retention-purge":
        with SessionLocal() as db:
            result = retention_purge(db, apply=args.apply, max_batches=args.max_batches)
        print(json.dumps(result, indent=2))
        return 0

    password = os.environ.get(PASSWORD_ENV, "")
    with SessionLocal() as db:
        try:
            username = create_first_admin(db, args.username, args.email, password, args.full_name).username
        except BootstrapRefused as e:
            print(f"create-admin refused: {e}", file=sys.stderr)
            return 1
    print(f"ADMIN '{username}' created; password change is required at first login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
