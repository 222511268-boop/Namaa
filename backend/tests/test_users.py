"""US02 Manage user accounts and roles: AC-02.1 to AC-02.5."""

import pytest

from app.models import Role
from tests.conftest import PASSWORD, login


def _new(email="new.manager@example.com", role="manager", password="a-strong-password", name="New Manager"):
    return {"email": email, "full_name": name, "role": role, "password": password}


def test_ac_02_1_admin_creates_account_that_can_sign_in(as_role, client):
    admin = as_role(Role.admin)
    r = admin.post("/api/users", json=_new())
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "manager" and r.json()["is_active"] is True
    assert login(client, "new.manager@example.com", "a-strong-password").status_code == 200


@pytest.mark.parametrize(
    "payload, field",
    [
        (_new(email="manager@example.com"), "email"),  # duplicate (existing fixture user)
        (_new(email="MANAGER@EXAMPLE.com"), "email"),  # duplicate, different case
        (_new(email="not-an-email"), "email"),
        (_new(password="short"), "password"),  # under 10 characters
        (_new(role="superuser"), "role"),
        (_new(name=" "), "full_name"),
    ],
)
def test_ac_02_1_invalid_account_details_rejected_with_field(as_role, payload, field):
    r = as_role(Role.admin).post("/api/users", json=payload)
    assert r.status_code == 422
    assert any(err["loc"][-1] == field for err in r.json()["detail"]), r.json()


def test_ac_02_2_role_change_applies_to_next_request(as_role, users):
    viewer = as_role(Role.viewer)
    assert viewer.get("/api/processing-runs").status_code == 403
    admin = as_role(Role.admin)
    r = admin.patch(f"/api/users/{users[Role.viewer].id}", json={"role": "manager"})
    assert r.status_code == 200 and r.json()["role"] == "manager"
    assert viewer.get("/api/processing-runs").status_code == 200


def test_ac_02_3_deactivation_revokes_sessions_and_blocks_sign_in(as_role, users, client):
    inspector = as_role(Role.inspector)
    assert inspector.get("/api/sites").status_code == 200
    admin = as_role(Role.admin)
    assert admin.patch(f"/api/users/{users[Role.inspector].id}", json={"is_active": False}).status_code == 200
    assert inspector.get("/api/sites").status_code == 401  # open session ended
    assert login(client, "inspector@example.com").status_code == 401  # cannot sign in
    assert admin.patch(f"/api/users/{users[Role.inspector].id}", json={"is_active": True}).status_code == 200
    assert login(client, "inspector@example.com", PASSWORD).status_code == 200


@pytest.mark.parametrize("role", [Role.manager, Role.inspector, Role.viewer])
def test_ac_02_4_non_admins_cannot_manage_users(as_role, users, role):
    c = as_role(role)
    assert c.get("/api/users").status_code == 403
    assert c.post("/api/users", json=_new(email="x@example.com")).status_code == 403
    assert c.patch(f"/api/users/{users[Role.viewer].id}", json={"role": "admin"}).status_code == 403


def test_ac_02_5_admin_cannot_lock_themselves_out(as_role, users):
    admin = as_role(Role.admin)
    me = users[Role.admin].id
    r1 = admin.patch(f"/api/users/{me}", json={"is_active": False})
    r2 = admin.patch(f"/api/users/{me}", json={"role": "manager"})
    assert r1.status_code == r2.status_code == 422
    assert admin.get("/api/users").status_code == 200  # still an active admin


def test_unknown_user_returns_404(as_role):
    r = as_role(Role.admin).patch("/api/users/00000000-0000-0000-0000-000000000000", json={"role": "viewer"})
    assert r.status_code == 404
