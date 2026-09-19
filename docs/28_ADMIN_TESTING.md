# 28 Admin Testing

## Isolated Database Environment
- The exact Phase04 destructive test DB is guaranteed to be `spnc_phase04_admin_test`.
- A mandatory DB guard `assert_safe_phase04_test_database` is invoked prior to any destructive operation, checking that the database name exactly matches the expected DB URL.

## Architecture
- Real backend implementations (routers, dependencies, databases, schemas) are fully tested in End-to-End integration tests.
- Fast validation tests mock nothing, using real FastAPI routers and real authentication via JWT.

## Concurrency
- `test_concurrent_admin_demotion_preserves_one_usable_admin` asserts via multi-threading and a synchronization Barrier that independent DB sessions cannot produce 0 admins during concurrent mutations.
- Real advisory locks are used instead of stubs.

## Test Commands
- Admin test suite: `venv\Scripts\python.exe -m pytest tests\api\test_admin.py tests\api\test_db_guard.py -v`
- Set `DATABASE_URL` for regressions (e.g. `$env:DATABASE_URL="postgresql://spnc_test:spnc_test_password@localhost:5432/spnc_phase03_auth_test"`).

## No-Placeholder Policy
Phase04 strictly prohibits dummy checks, stubbed tests, or weak placeholder tests (`pass`, `assert True`, `.skip`). Every test MUST contain meaningful verification of expected functionality and data models.
