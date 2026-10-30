"""Writes the backend OpenAPI schema to apps/web/openapi.json (docs/46 D3).

No server, database or network is needed: the schema comes from app.openapi().
Usage (from the repository root): python scripts/web/dump_openapi.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
# Settings require a URL; nothing connects to it while building the schema
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")

from app.main import app  # noqa: E402

out = ROOT / "apps" / "web" / "openapi.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
print(f"wrote {out.relative_to(ROOT)}")
