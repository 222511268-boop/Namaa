"""US01 Sign in securely: AC-01.1 to AC-01.5."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models import Role, UserSession
from app.routers.auth import INVALID_LOGIN
from tests.conftest import PASSWORD, login


def test_ac_01_1_valid_login_sets_httponly_session_cookie(client, users):
    r = login(client, "manager@example.com")
    assert r.status_code == 200
    assert r.json()["role"] == "manager"
    cookie = r.headers["set-cookie"]
    assert "namaa_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/auth/me").json()["email"] == "manager@example.com"


def test_ac_01_1_email_is_case_insensitive(client, users):
    assert login(client, "  Manager@Example.COM ").status_code == 200


def test_ac_01_2_unknown_email_and_wrong_password_look_identical(client, users):
    wrong_pw = login(client, "manager@example.com", "not-the-password")
    unknown = login(client, "nobody@example.com", PASSWORD)
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json() == {"detail": INVALID_LOGIN}
    assert "set-cookie" not in wrong_pw.headers


def test_ac_01_3_logout_revokes_session_server_side(client, users):
    login(client, "viewer@example.com")
    old_cookie = client.cookies.get("namaa_session")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("namaa_session", old_cookie)  # replay the old cookie
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/sites").status_code == 401


def test_ac_01_4_protected_endpoints_require_session(client):
    for path in (
        "/api/auth/me",
        "/api/sites",
        "/api/sites/geojson",
        "/api/districts",
        "/api/summary",
        "/api/users",
        "/api/processing-runs",
    ):
        assert client.get(path).status_code == 401, path


def test_ac_01_4_forged_cookie_rejected(client, users):
    client.cookies.set("namaa_session", "forged-token-value")
    assert client.get("/api/auth/me").status_code == 401


def test_ac_01_5_expired_session_rejected(client, users, db):
    login(client, "viewer@example.com")
    db.execute(update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_session_token_stored_only_as_hash(client, users, db):
    login(client, "viewer@example.com")
    token = client.cookies.get("namaa_session")
    stored = db.query(UserSession).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64


def test_inactive_user_gets_same_generic_message(client, users, db):
    users[Role.inspector].is_active = False
    db.commit()
    r = login(client, "inspector@example.com")
    assert r.status_code == 401 and r.json()["detail"] == INVALID_LOGIN
