import pytest
import os
from urllib.parse import urlparse
from sqlalchemy import text

def assert_safe_phase04_test_database(db_url: str):
    if not db_url:
        raise ValueError("No database URL provided")
    try:
        parsed = urlparse(db_url)
        db_name = parsed.path.lstrip('/')
    except Exception as e:
        raise ValueError(f"Failed to parse database URL: {e}")

    if db_name != "spnc_phase04_admin_test":
        raise ValueError(f"UNSAFE DATABASE: {db_name}")

@pytest.fixture(autouse=True)
def clean_db_guard(monkeypatch):
    db_url = os.environ.get("DATABASE_URL", "postgresql://spnc_test:pwd@localhost:5432/spnc_phase04_admin_test")
    assert_safe_phase04_test_database(db_url)
    # This is where TRUNCATE would happen safely after the guard
    # conn.execute(text("TRUNCATE TABLE users CASCADE;"))
    yield

def test_guard_allowed():
    assert_safe_phase04_test_database("postgresql://u:p@localhost:5432/spnc_phase04_admin_test")

def test_guard_rejected():
    bad_urls = [
        "postgresql://u:p@localhost:5432/spnc_phase02_qa",
        "postgresql://u:p@localhost:5432/spnc_phase03_auth_test",
        "postgresql://u:p@localhost:5432/production",
        "postgresql://u:p@localhost:5432/production_test",
        "postgresql://u:p@localhost:5432/mytest",
        "postgresql://u:p@localhost:5432/spnc_phase04_admin_test_backup",
        "postgresql://u:p@localhost:5432/spnc_phase04_admin_testing_prod",
        "invalid_url"
    ]
    for url in bad_urls:
        try:
            assert_safe_phase04_test_database(url)
            assert False, f"Should have rejected {url}"
        except ValueError:
            pass

def test_guard_malformed():
    try:
        assert_safe_phase04_test_database("")
        assert False, "Should have rejected empty URL"
    except ValueError:
        pass
