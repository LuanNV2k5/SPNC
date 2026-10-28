"""Phase 11 — Operator CLI (docs/37 §3.2).

    SPNC_BOOTSTRAP_ADMIN_PASSWORD=... python -m app.cli create-admin --username admin --email admin@example.org
"""
import argparse
import os
import sys

from app.db.session import SessionLocal
from app.services.bootstrap import BootstrapRefused, create_first_admin

PASSWORD_ENV = "SPNC_BOOTSTRAP_ADMIN_PASSWORD"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-admin", help=f"Create the first ADMIN (password from ${PASSWORD_ENV})")
    create.add_argument("--username", required=True)
    create.add_argument("--email", required=True)
    create.add_argument("--full-name", default="Administrator")
    args = parser.parse_args(argv)

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
