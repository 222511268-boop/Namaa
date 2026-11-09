import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_only
from app.models import Role, User, UserSession
from app.schemas import ResetLinkOut, UserCreate, UserOut, UserUpdate
from app.security import hash_password
from app.services.accounts import issue_reset_link
from app.services.audit import record

router = APIRouter(prefix="/api/users", tags=["users"])


def _field_error(field: str, msg: str) -> HTTPException:
    return HTTPException(422, [{"loc": ["body", field], "msg": msg, "type": "value_error"}])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return list(db.scalars(select(User).order_by(User.is_active.desc(), User.full_name)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    email = body.email.strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise _field_error("email", "An account with this email already exists.")
    user = User(email=email, full_name=body.full_name, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    record(
        db,
        admin,
        "user.created",
        f"Created {user.full_name} ({user.email}) as {user.role.value}",
        "user",
        user.id,
        {"email": user.email, "role": user.role.value},
        commit=False,
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if user.id == admin.id:
        if body.is_active is False:
            raise _field_error("is_active", "You cannot deactivate your own account.")
        if body.role is not None and body.role != Role.admin:
            raise _field_error("role", "You cannot remove your own administrator role.")
    events = []
    if body.full_name is not None and body.full_name.strip() != user.full_name:
        events.append(
            (
                "user.updated",
                f"Renamed {user.full_name} to {body.full_name.strip()}",
                {"from": user.full_name, "to": body.full_name.strip()},
            )
        )
        user.full_name = body.full_name.strip()
    if body.role is not None and body.role != user.role:
        events.append(
            (
                "user.role_changed",
                f"Changed {user.full_name}'s role from {user.role.value} to {body.role.value}",
                {"from": user.role.value, "to": body.role.value},
            )
        )
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        events.append(
            (
                "user.reactivated" if body.is_active else "user.deactivated",
                f"{'Reactivated' if body.is_active else 'Deactivated'} {user.full_name}",
                {},
            )
        )
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            # End every open session of the deactivated user immediately.
            db.execute(
                update(UserSession)
                .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
    for action, summary, details in events:
        record(db, admin, action, summary, "user", user.id, details, commit=False)
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-link", response_model=ResetLinkOut, status_code=status.HTTP_201_CREATED)
def create_reset_link(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """Issue a single-use password reset link. The link is returned once and only its hash is stored."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if not user.is_active:
        raise _field_error("user", "Reactivate the account before issuing a reset link.")
    url, expires = issue_reset_link(db, user, admin)
    record(
        db,
        admin,
        "user.reset_link",
        f"Issued a password reset link for {user.full_name}",
        "user",
        user.id,
        {"expires_at": expires.isoformat()},
    )
    return {"url": url, "expires_at": expires}
