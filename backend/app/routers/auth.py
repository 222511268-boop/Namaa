from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_session
from app.models import User, UserSession
from app.schemas import ChangePasswordBody, LoginRequest, ResetCheckBody, ResetPasswordBody, UserOut
from app.security import hash_token, new_session_token, verify_password
from app.services import accounts
from app.services.accounts import AccountError
from app.services.audit import record

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID_LOGIN = "Email or password is incorrect."


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    password_ok = verify_password(body.password, user.password_hash if user else None)
    # Same status and message for unknown email, wrong password and inactive account.
    if user is None or not password_ok or not user.is_active:
        # Only the submitted email is kept (never the password); the reason is not recorded.
        record(
            db,
            None,
            "auth.sign_in_failed",
            f"Sign-in failed for {body.email.strip()[:200]}",
            "user",
            user.id if user else None,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(hours=s.session_ttl_hours),
        )
    )
    record(db, user, "auth.sign_in", f"{user.full_name} signed in", "user", user.id)
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)):
    session = db.merge(session)
    session.revoked_at = datetime.now(UTC)
    record(db, session.user, "auth.sign_out", f"{session.user.full_name} signed out", "user", session.user_id)
    response.delete_cookie(get_settings().session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(session: UserSession = Depends(get_current_session)):
    return session.user


# ---------------------------------------------------------------- account recovery (US25)


def _account_error(exc: AccountError) -> HTTPException:
    if exc.field:
        return HTTPException(422, [{"loc": ["body", exc.field], "msg": str(exc), "type": "value_error"}])
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordBody, session: UserSession = Depends(get_current_session), db: Session = Depends(get_db)
):
    try:
        accounts.change_password(db, session.user, session, body.current_password, body.new_password)
    except AccountError as exc:
        raise _account_error(exc) from exc
    user = session.user
    record(db, user, "auth.password_changed", f"{user.full_name} changed their password", "user", user.id)


@router.post("/reset-password/check")
def check_reset_link(body: ResetCheckBody, db: Session = Depends(get_db)):
    """Public: confirm a reset link is usable before showing the form."""
    try:
        user = accounts.check_reset_token(db, body.token)
    except AccountError as exc:
        raise _account_error(exc) from exc
    return {"full_name": user.full_name}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetPasswordBody, db: Session = Depends(get_db)):
    """Public: set a new password with a valid single-use link; all of the user's sessions end."""
    try:
        user = accounts.reset_password(db, body.token, body.new_password)
    except AccountError as exc:
        raise _account_error(exc) from exc
    record(db, user, "auth.password_reset", f"{user.full_name} set a new password with a reset link", "user", user.id)
