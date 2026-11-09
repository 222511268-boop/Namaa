"""US24: activity record. Key actions are logged with user and time; read-only; filterable; no secrets."""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, Role
from tests.conftest import PASSWORD, login, square


@pytest.fixture
def admin(as_role):
    return as_role(Role.admin)


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


def _events(admin, **params):
    r = admin.get("/api/activity", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _actions(admin, **params):
    return [e["action"] for e in _events(admin, limit=200, **params)["items"]]


def test_ac_24_1_sign_ins_and_failures_logged_with_user_and_time(client, users, admin):
    assert login(client, users[Role.viewer].email).status_code == 200
    assert login(client, users[Role.viewer].email, "wrong-password").status_code == 401
    items = _events(admin, category="auth")["items"]
    ok = next(e for e in items if e["action"] == "auth.sign_in" and e["user_name"] == users[Role.viewer].full_name)
    assert ok["at"] and ok["user_role"] == "viewer"
    failed = next(e for e in items if e["action"] == "auth.sign_in_failed")
    assert users[Role.viewer].email in failed["summary"] and failed["user_id"] is None


def test_ac_24_1_role_change_and_account_events(admin, users):
    uid = str(users[Role.viewer].id)
    assert admin.patch(f"/api/users/{uid}", json={"role": "manager"}).status_code == 200
    assert admin.patch(f"/api/users/{uid}", json={"is_active": False}).status_code == 200
    ev = _events(admin, entity_id=uid)["items"]
    role = next(e for e in ev if e["action"] == "user.role_changed")
    assert role["details"] == {"from": "viewer", "to": "manager"}
    assert role["user_name"] == users[Role.admin].full_name
    assert any(e["action"] == "user.deactivated" for e in ev)


def test_ac_24_1_site_edits_review_decisions_and_task_changes(admin, manager, as_role, users, db):
    import uuid as _uuid

    from app.services.analysis import analyse_sites
    from tests.analysis_helpers import add_observations, history, latest

    site = manager.post(
        "/api/sites",
        json={"name": "Audit Park", "site_type": "park", "planting_category": "turf",
              "geometry": square(46.705, 24.705, 0.003)},
    ).json()
    upd = manager.put(f"/api/sites/{site['id']}", json={"name": "Audit Park 2", "site_type": "park",
                                                        "planting_category": "shrubs"})
    assert upd.status_code == 200
    add_observations(db, _uuid.UUID(site["id"]), history(0.35, 0.03, 0.01, [2025]) +
                     latest([("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]))
    analyse_sites(db)
    sig = manager.get("/api/signals").json()[0]
    task = manager.post(f"/api/signals/{sig['id']}/inspection", json={
        "title": "Check turf", "priority": "high", "due_date": (date.today() + timedelta(days=2)).isoformat(),
        "assignee_id": str(users[Role.inspector].id)}).json()
    insp = as_role(Role.inspector)
    assert insp.post(f"/api/tasks/{task['id']}/start").status_code == 200
    acts = _actions(admin)
    for expected in ("site.created", "site.updated", "signal.sent_for_inspection", "task.started"):
        assert expected in acts, expected
    edit = _events(admin, action="site.updated")["items"][0]
    assert edit["details"]["name"] == {"from": "Audit Park", "to": "Audit Park 2"}
    assert edit["details"]["planting_category"] == {"from": "turf", "to": "shrubs"}


def test_ac_24_2_log_is_read_only(admin, db, client, users):
    login(client, users[Role.viewer].email)
    # No write endpoints exist for the log.
    assert admin.post("/api/activity", json={}).status_code == 405
    assert admin.delete("/api/activity").status_code == 405
    # The database itself rejects updates and deletes.
    eid = db.query(AuditEvent.id).first()[0]
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE audit_events SET summary = 'x' WHERE id = :i"), {"i": eid})
    db.rollback()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM audit_events WHERE id = :i"), {"i": eid})
    db.rollback()


def test_ac_24_2_only_administrators_can_read(as_role):
    for role in (Role.manager, Role.inspector, Role.viewer):
        assert as_role(role).get("/api/activity").status_code == 403


def test_ac_24_3_filters(admin, client, users):
    login(client, users[Role.viewer].email)
    login(client, users[Role.manager].email)
    viewer_id = str(users[Role.viewer].id)
    only_viewer = _events(admin, user_id=viewer_id)["items"]
    assert only_viewer and all(e["user_id"] == viewer_id for e in only_viewer)
    assert all(a == "auth.sign_in" for a in _actions(admin, action="auth.sign_in"))
    assert _events(admin, q="Test Manager")["total"] >= 1
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert _events(admin, start=tomorrow)["total"] == 0
    page = _events(admin, limit=1)
    assert len(page["items"]) == 1 and page["total"] >= 3


def test_ac_24_4_no_passwords_or_tokens_in_log(admin, users, client, db):
    login(client, users[Role.viewer].email)
    link = admin.post(f"/api/users/{users[Role.inspector].id}/reset-link").json()
    token = link["url"].split("token=")[1]
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "brand-new-password-1"}
                       ).status_code == 204
    viewer = login(client, users[Role.viewer].email)
    cookie = viewer.cookies.get("namaa_session") or client.cookies.get("namaa_session")
    dump = json.dumps([
        {"s": e.summary, "d": e.details} for e in db.query(AuditEvent).all()
    ])
    for secret in (PASSWORD, "brand-new-password-1", token, cookie, users[Role.viewer].password_hash):
        assert secret and secret not in dump
    assert "auth.password_reset" in _actions(admin)
    assert "user.reset_link" in _actions(admin)


def test_record_drops_secret_like_detail_keys(db):
    from app.services.audit import record

    e = record(db, None, "auth.sign_in", "x", details={"password": "p", "api_key": "k", "nested": {"token": "t"},
                                                      "ok": 1})
    assert e.details == {"nested": {}, "ok": 1}
    with pytest.raises(ValueError):
        record(db, None, "made.up", "x")
