# 25 Admin Module

## Scope
The Phase 04 Admin Module handles system-wide user/account administration, system-wide class and exam read boundaries, exam cancellation, basic allowlisted settings (retention_days), audit log visibility, and a dashboard summary.

## Explicit Non-Scope
The Admin Module does not handle Phase 05 authoring, teacher/student workflows, problem authoring, or academic content editing outside of B11 requirements.

## Module Architecture
- Router (`app/api/endpoints/admin.py`) for HTTP handling.
- Service (`app/services/admin.py`) for business logic and invariant validation.
- Repository (`app/repositories/admin.py`) for database queries and pagination.

## Components
- **User Administration**: Listing, creating, updating, and viewing users.
- **Class Admin Boundary**: Viewing classes across the system.
- **Exam Admin Boundary**: Viewing exams and executing cancellations.
- **Settings**: Modifying allowlisted system settings.
- **Audit**: Reading system audit logs.
- **Dashboard**: Providing summary metrics.
- **Last-Usable-Admin Invariant**: Guarantees at least one active Admin exists at all times, protected with a PostgreSQL advisory lock.
