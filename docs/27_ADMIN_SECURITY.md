# 27 Admin Security

## Authorization
- Backend Admin authorization enforced via Phase03 RBAC checks.
- All Phase04 API operations restrict non-Admin requests, rejecting anonymous users (401), teachers (403), and students (403).

## Data Protection
- PII and credentials (password hashes, refresh tokens, active access tokens) are strictly excluded from API responses.
- Active audit logs intentionally exclude sensitive credentials from payloads.

## State Enforcement
- The backend evaluates the *authoritative* account state. Locked or pending Admins using previously acquired valid tokens are denied access (401 Unauthorized/USER_LOCKED).

## Write Policies
- Password handling: Plaintext passwords are never persisted.
- System Settings: Strongly typed and explicitly allowlisted to prevent arbitrary configuration writes or injection.

## Concurrent Last-Admin Invariant Protection
- It is enforced that at least 1 Admin user remains active at all times.
- Safe serialization using PostgreSQL transaction advisory locks (`SELECT pg_advisory_xact_lock(72946281)`).
- Strict ordering is maintained by locking before evaluating the remaining usable admin count. This safely guarantees that concurrent database sessions cannot independently demote the final two Admins into zero Admins.
