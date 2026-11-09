"""US25 Recover account access: administrator reset links and self-service password change."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import update

from app.models import PasswordResetToken, Role
from app.security import hash_token
from tests.conftest import PASSWORD, login

NEW = "a-brand-new-password"


def token_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["token"][0]


@pytest.fixture
def link(as_role, users):
    r = as_role(Role.admin).post(f"/api/users/{users[Role.viewer].id}/reset-link")
    assert r.status_code == 201, r.text
    return r.json()


def test_ac_25_1_link_issued_once_and_only_hash_stored(link, db):
    assert "/reset-password?token=" in link["url"]
    token = token_of(link["url"])
    stored = db.query(PasswordResetToken).one()
    assert stored.token_hash == hash_token(token) and token not in stored.token_hash
    expires = datetime.fromisoformat(link["expires_at"])
    assert timedelta(hours=23) < expires - datetime.now(UTC) <= timedelta(hours=24)


def test_ac_25_2_reset_sets_password_and_ends_sessions(link, as_role, client):
    viewer = as_role(Role.viewer)  # an existing session
    token = token_of(link["url"])
    assert client.post("/api/auth/reset-password/check", json={"token": token}).json() == {"full_name": "Test Viewer"}
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": NEW})
    assert r.status_code == 204
    assert viewer.get("/api/auth/me").status_code == 401  # earlier sessions ended
    assert login(client, "viewer@example.com", PASSWORD).status_code == 401
    assert login(client, "viewer@example.com", NEW).status_code == 200


def test_ac_25_2_password_rules_apply(link, client):
    r = client.post("/api/auth/reset-password", json={"token": token_of(link["url"]), "new_password": "short"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "new_password"
    r = client.post("/api/auth/reset-password", json={"token": token_of(link["url"]), "new_password": PASSWORD})
    assert r.status_code == 422 and "different" in r.json()["detail"][0]["msg"]


def test_ac_25_3_used_link_rejected(link, client):
    token = token_of(link["url"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": NEW})
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "another-password-1"})
    assert r.status_code == 400 and "invalid or has expired" in r.json()["detail"]


def test_ac_25_3_expired_link_rejected(link, client, db):
    db.execute(update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    db.commit()
    r = client.post("/api/auth/reset-password/check", json={"token": token_of(link["url"])})
    assert r.status_code == 400


def test_ac_25_3_superseded_and_invalid_links_rejected(link, as_role, users, client):
    as_role(Role.admin).post(f"/api/users/{users[Role.viewer].id}/reset-link")  # new link replaces the first
    assert client.post("/api/auth/reset-password/check", json={"token": token_of(link["url"])}).status_code == 400
    assert client.post("/api/auth/reset-password/check", json={"token": "x" * 43}).status_code == 400


def test_reset_link_not_issued_for_deactivated_user(as_role, users):
    admin = as_role(Role.admin)
    admin.patch(f"/api/users/{users[Role.viewer].id}", json={"is_active": False})
    assert admin.post(f"/api/users/{users[Role.viewer].id}/reset-link").status_code == 422


@pytest.mark.parametrize("role", [Role.manager, Role.inspector, Role.viewer])
def test_ac_25_5_only_admin_issues_links(as_role, users, role):
    assert as_role(role).post(f"/api/users/{users[Role.viewer].id}/reset-link").status_code == 403


def test_ac_25_4_change_own_password(users, client, as_role):
    me = as_role(Role.inspector)
    other_session = as_role(Role.inspector)
    r = me.post("/api/auth/change-password", json={"current_password": "wrong-password", "new_password": NEW})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "current_password"
    assert (
        me.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW}).status_code
        == 204
    )
    assert me.get("/api/auth/me").status_code == 200  # current session kept
    assert other_session.get("/api/auth/me").status_code == 401  # other sessions ended
    assert login(client, "inspector@example.com", NEW).status_code == 200
