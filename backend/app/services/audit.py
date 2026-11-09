"""Activity record (US24): an append-only log of key actions with the user and time.

Entries never contain passwords, session tokens, reset tokens or API keys: callers pass only the fields listed
in each action, and `record` drops any detail whose key looks like a secret as a second safeguard.
"""

import re

from sqlalchemy.orm import Session

from app.models import AuditEvent, User

ACTIONS = {
    "auth.sign_in": "Signed in",
    "auth.sign_in_failed": "Sign-in failed",
    "auth.sign_out": "Signed out",
    "auth.password_changed": "Changed password",
    "auth.password_reset": "Reset password with a link",
    "user.created": "Created account",
    "user.updated": "Updated account",
    "user.role_changed": "Changed role",
    "user.deactivated": "Deactivated account",
    "user.reactivated": "Reactivated account",
    "user.reset_link": "Issued password reset link",
    "site.created": "Created green space",
    "site.updated": "Edited green space",
    "site.status_changed": "Changed green space status",
    "site.imported": "Imported green spaces",
    "schedule.created": "Added irrigation schedule",
    "schedule.updated": "Edited irrigation schedule",
    "schedule.deleted": "Removed irrigation schedule",
    "plant_factor.updated": "Changed plant factor",
    "signal.dismissed": "Dismissed signal",
    "signal.confirmed": "Confirmed signal",
    "signal.sent_for_inspection": "Sent signal for inspection",
    "signal.outcome_recorded": "Recorded signal outcome",
    "task.created": "Created task",
    "task.updated": "Edited task",
    "task.cancelled": "Cancelled task",
    "task.started": "Started task",
    "task.findings_saved": "Saved findings",
    "task.completed": "Completed task",
    "run.queued": "Started processing run",
    "ai.signal_brief": "Generated AI evidence brief",
    "ai.overview_summary": "Generated AI overview summary",
    "ai.failed": "AI request failed",
}

_SECRET_KEY = re.compile(r"pass(word)?|token|secret|api[_-]?key|cookie|hash|authorization", re.I)


def _clean(details: dict) -> dict:
    out = {}
    for k, v in details.items():
        if _SECRET_KEY.search(k):
            continue
        out[k] = _clean_value(v)
    return out


def _clean_value(value):
    if isinstance(value, dict):
        return _clean(value)
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    return value


def record(
    db: Session,
    user: User | None,
    action: str,
    summary: str,
    entity_type: str | None = None,
    entity_id=None,
    details: dict | None = None,
    commit: bool = True,
) -> AuditEvent:
    """Append one entry. The caller's transaction is committed unless commit=False."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown audit action {action!r}")
    event = AuditEvent(
        user_id=user.id if user else None,
        user_name=user.full_name if user else None,
        user_role=user.role.value if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary[:300],
        details=_clean(details or {}),
    )
    db.add(event)
    if commit:
        db.commit()
    return event
