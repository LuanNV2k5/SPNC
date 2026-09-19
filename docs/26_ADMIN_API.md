# 26 Admin API

## Endpoints

### User Administration
- `GET /api/v1/admin/users`: List users (Pagination: `page`, `size`)
- `POST /api/v1/admin/users`: Create a new user (Role: ADMIN, TEACHER, STUDENT)
- `GET /api/v1/admin/users/{user_id}`: Retrieve user details
- `PATCH /api/v1/admin/users/{user_id}`: Update user role or status

### Class Admin
- `GET /api/v1/admin/classes`: List classes (Pagination)
- `GET /api/v1/admin/classes/{class_id}`: Class details

### Exam Admin
- `GET /api/v1/admin/exams`: List exams (Pagination)
- `GET /api/v1/admin/exams/{exam_id}`: Exam details
- `PATCH /api/v1/admin/exams/{exam_id}/cancel`: Cancel an exam (Error: `INVALID_STATE` if COMPLETED)

### Audit and Dashboard
- `GET /api/v1/admin/audit-logs`: List audit logs (Pagination)
- `GET /api/v1/admin/dashboard/summary`: Get aggregate system metrics

### Settings
- `GET /api/v1/admin/settings`: Read system settings
- `PATCH /api/v1/admin/settings`: Update settings (Allows `retention_days` within valid ranges)

## Authorization
All endpoints require a valid Bearer token for an active `ADMIN` user.

## Pagination
Pagination uses `page` and `size` parameters with a maximum `size` of 100.
