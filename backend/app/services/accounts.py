"""Account recovery (US25): administrator-issued reset links and self-service password change."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PasswordResetToken, User, UserSession
from app.security import hash_password, hash_token, new_session_token, verify_password

INVALID_LINK = "This reset link is invalid or has expired. Ask your administrator for a new one."


class AccountError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def _revoke_sessions(db: Session, user_id, keep_session_id=None) -> None:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if keep_session_id is not None:
        q = q.where(UserSession.id != keep_session_id)
    db.execute(q.values(revoked_at=datetime.now(UTC)))


def issue_reset_link(db: Session, user: User, admin: User) -> tuple[str, datetime]:
    """Create a single-use link; earlier unused links for the user stop working. Returns (url, expiry)."""
    s = get_settings()
    now = datetime.now(UTC)
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)  # superseded
    )
    token = new_session_token()
    expires = now + timedelta(hours=s.reset_token_ttl_hours)
    db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(token), expires_at=expires, created_by=admin.id))
    db.commit()
    return f"{s.public_base_url.rstrip('/')}/reset-password?token={token}", expires


def _valid_token(db: Session, token: str) -> PasswordResetToken:
    rec = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    if rec is None or rec.used_at is not None or rec.expires_at <= datetime.now(UTC) or not rec.user.is_active:
        raise AccountError(INVALID_LINK)
    return rec


def check_reset_token(db: Session, token: str) -> User:
    return _valid_token(db, token).user


def reset_password(db: Session, token: str, new_password: str) -> User:
    rec = _valid_token(db, token)
    user = rec.user
    if verify_password(new_password, user.password_hash):
        raise AccountError("Choose a password different from the previous one.", field="new_password")
    user.password_hash = hash_password(new_password)
    rec.used_at = datetime.now(UTC)
    _revoke_sessions(db, user.id)
    db.commit()
    return user


def change_password(db: Session, user: User, session: UserSession, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AccountError("The current password is incorrect.", field="current_password")
    if current == new:
        raise AccountError("Choose a password different from the current one.", field="new_password")
    user.password_hash = hash_password(new)
    _revoke_sessions(db, user.id, keep_session_id=session.id)
    db.commit()
