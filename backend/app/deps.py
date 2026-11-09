"""Request dependencies: current user and role checks."""

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Role, User, UserSession
from app.security import hash_token


def get_current_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or session.expires_at <= now or not session.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Please sign in again.")
    return session


def get_current_user(session: UserSession = Depends(get_current_session)) -> User:
    return session.user


def require_roles(*roles: Role) -> Callable[[User], User]:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action.")
        return user

    return checker


# Permission groups (the permission matrix enforced by every endpoint).
any_user = get_current_user
admin_only = require_roles(Role.admin)
site_editors = require_roles(Role.manager)
processing_operators = require_roles(Role.admin, Role.manager)
signal_viewers = require_roles(Role.admin, Role.manager)
task_viewers = require_roles(Role.admin, Role.manager, Role.inspector)
overview_viewers = require_roles(Role.admin, Role.manager, Role.viewer)
ai_summary_users = require_roles(Role.manager, Role.viewer)
