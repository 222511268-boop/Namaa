"""Start-up and setup tasks."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Role, User
from app.security import hash_password

log = logging.getLogger("namaa.bootstrap")


def ensure_bootstrap_admin(db: Session) -> User | None:
    """Create the first administrator from environment variables when no administrator exists."""
    s = get_settings()
    if db.scalar(select(User.id).where(User.role == Role.admin).limit(1)):
        return None
    if not s.bootstrap_admin_email or not s.bootstrap_admin_password:
        log.warning("No administrator exists and BOOTSTRAP_ADMIN_EMAIL/PASSWORD are not set.")
        return None
    if len(s.bootstrap_admin_password) < 10:
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must have at least 10 characters.")
    user = User(
        email=s.bootstrap_admin_email.strip().lower(),
        full_name=s.bootstrap_admin_name,
        role=Role.admin,
        password_hash=hash_password(s.bootstrap_admin_password),
    )
    db.add(user)
    db.commit()
    log.info("Created bootstrap administrator %s", user.email)
    return user
