# 29 Admin Traceability

| ID | Requirement | Implementation | Test Evidence |
|----|-------------|----------------|---------------|
| ADM01 | List users | `GET /api/v1/admin/users` | `test_list_users` |
| ADM02 | User pagination | `admin_repo.get_users_paginated` | `test_list_users` |
| ADM03 | User details | `GET /api/v1/admin/users/{id}` | `test_get_user` |
| ADM04 | Create Admin | `POST /api/v1/admin/users` | `test_create_user` |
| ADM05 | Create Teacher | `POST /api/v1/admin/users` | `test_create_user` |
| ADM06 | Create Student | `POST /api/v1/admin/users` | `test_create_user` |
| ADM07 | Hashed password | `get_password_hash` | `test_create_user` |
| ADM08 | Plaintext omitted | `AdminUserDetailResponse` | `test_create_user` |
| ADM09 | Validation rules | `update_user` | `test_create_user_invalid_role` |
| ADM10 | Update profile | `PATCH /users/{id}` | `test_update_user_role` |
| ADM11 | Update role | `PATCH /users/{id}` | `test_update_user_role` |
| ADM12 | Update status | `PATCH /users/{id}` | `test_single_admin_status_change` |
| ADM21 | List classes | `GET /api/v1/admin/classes` | `test_list_classes` |
| ADM22 | Class details | `GET /classes/{id}` | `test_get_class` |
| ADM31 | List exams | `GET /api/v1/admin/exams` | `test_list_exams` |
| ADM32 | Exam details | `GET /exams/{id}` | `test_list_exams` |
| ADM33 | Cancel exam | `PATCH /exams/{id}/cancel` | `test_cancel_exam` |
| ADM41 | Read settings | `GET /api/v1/admin/settings` | `test_get_settings` |
| ADM42 | Update settings | `PATCH /settings` | `test_update_settings` |
| ADM51 | Read audit logs | `GET /audit-logs` | `test_audit_logs` |
| ADM60 | Dashboard summary | `GET /dashboard/summary` | `test_dashboard_summary` |

| ID | Requirement | Implementation | Test Evidence |
|----|-------------|----------------|---------------|
| SEC-ADM01 | Hide sensitive fields | `AdminUserDetailResponse` | `test_get_user` |
| SEC-ADM02 | No password hashes | `AdminUserDetailResponse` | `test_get_user` |
| SEC-ADM03 | Anonymous denial | `require_admin` | `test_anonymous_access_unauthorized` |
| SEC-ADM04 | Teacher denial | `require_admin` | `test_teacher_access_forbidden` |
| SEC-ADM05 | Student denial | `require_admin` | `test_student_access_forbidden` |
| SEC-ADM06 | Stale token denial | `require_admin` | `test_stale_token_rejected` |
| SEC-ADM07 | Last-admin sequential | `update_user` | `test_single_admin_role_change` |
| SEC-ADM08 | Last-admin concurrency | `acquire_last_admin_lock` | `test_concurrent_admin_demotion_preserves_one_usable_admin` |
| SEC-ADM09 | Error contract | `HTTPException` | `test_stale_token_rejected` |
| SEC-ADM10 | No destructive escape | `assert_safe_phase04_test_database` | `test_db_guard.py` |
