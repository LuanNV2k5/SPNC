"""Phase 11 — First-admin bootstrap (docs/37 §3.2, D4).

Creates the first ADMIN of an empty system. Refuses when any ADMIN exists, so it cannot be
used to add administrators later. The caller supplies the password from the environment;
it is never logged.
"""
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.user import AccountStatus, AuditLog, User

MIN_PASSWORD_LENGTH = 12
_EMAIL = TypeAdapter(EmailStr)


class BootstrapRefused(Exception):
    pass


def create_first_admin(db: Session, username: str, email: str, password: str, full_name: str = "Administrator") -> User:
    try:
        # Same rule as API responses (EmailStr); an address they reject would make /auth/me fail
        email = _EMAIL.validate_python(email)
    except ValidationError:
        raise BootstrapRefused("Invalid email address (reserved domains such as .local or .test are not accepted)")
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise BootstrapRefused(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    # Serialize concurrent bootstraps (transaction-scoped advisory lock)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('spnc_bootstrap_admin'))"))
    if db.scalar(select(func.count(User.id)).where(User.role == "ADMIN")):
        raise BootstrapRefused("An ADMIN already exists; create further accounts through the admin API")
    if db.scalar(select(func.count(User.id)).where((User.username == username) | (User.email == email))):
        raise BootstrapRefused("Username or email already in use")
    admin = User(
        username=username, email=email, password_hash=get_password_hash(password), full_name=full_name,
        role="ADMIN", status=AccountStatus.ACTIVE.value, force_password_change=True,
    )
    db.add(admin)
    db.flush()
    db.add(AuditLog(actor_id=None, action="ADMIN_BOOTSTRAPPED", target_type="USER", target_id=str(admin.id)))
    db.commit()
    return admin
