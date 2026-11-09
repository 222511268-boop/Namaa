"""US03 / NFR05: AC-03.2. Every protected endpoint enforces the Sprint 1 permission matrix on the server."""

import pytest

from app.models import Role
from tests.conftest import square

A, M, INS, V = Role.admin, Role.manager, Role.inspector, Role.viewer

SITE_BODY = {
    "name": "Matrix Park",
    "site_type": "park",
    "planting_category": "turf",
    "geometry": square(46.705, 24.705),
}

# (method, path, body, roles allowed)
MATRIX = [
    ("get", "/api/users", None, {A}),
    (
        "post",
        "/api/users",
        {"email": "m@example.com", "full_name": "Matrix", "role": "viewer", "password": "long-enough-pw"},
        {A},
    ),
    ("get", "/api/sites", None, {A, M, INS, V}),
    ("get", "/api/sites/geojson", None, {A, M, INS, V}),
    ("get", "/api/districts", None, {A, M, INS, V}),
    ("get", "/api/summary", None, {A, M, INS, V}),
    ("post", "/api/sites", SITE_BODY, {M}),
    ("post", "/api/imports/osm", {"district_id": 999999}, {M}),
    ("get", "/api/processing-runs", None, {A, M}),
    ("post", "/api/processing-runs", {"start_date": "2025-06-01", "end_date": "2025-06-30"}, {A, M}),
    # Sprint 2
    ("get", "/api/signals", None, {A, M}),
    ("get", "/api/tasks", None, {A, M, INS}),
    ("post", "/api/tasks", {"site_id": "00000000-0000-0000-0000-000000000000"}, {M}),
    ("get", "/api/inspectors", None, {M}),
    ("post", "/api/auth/change-password", {"current_password": "x", "new_password": "short"}, {A, M, INS, V}),
]


@pytest.mark.parametrize("method, path, body, allowed", MATRIX, ids=[f"{m.upper()} {p}" for m, p, _, _ in MATRIX])
@pytest.mark.parametrize("role", list(Role), ids=lambda r: r.value)
def test_ac_03_2_permission_matrix(as_role, district, method, path, body, allowed, role):
    c = as_role(role)
    r = getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)
    if role in allowed:
        assert r.status_code != 403, f"{role.value} should be allowed: {r.status_code} {r.text}"
    else:
        assert r.status_code == 403, f"{role.value} should be refused: {r.status_code} {r.text}"


@pytest.mark.parametrize("role", [A, INS, V])
def test_ac_03_2_only_managers_edit_existing_sites(as_role, district, role):
    site_id = as_role(M).post("/api/sites", json=SITE_BODY).json()["id"]
    c = as_role(role)
    assert c.put(f"/api/sites/{site_id}", json=SITE_BODY).status_code == 403
    assert c.patch(f"/api/sites/{site_id}/status", json={"status": "inactive"}).status_code == 403


def test_summary_hides_processing_details_from_inspectors_and_viewers(as_role):
    assert "latest_run" in as_role(M).get("/api/summary").json()
    assert "latest_run" not in as_role(V).get("/api/summary").json()
    assert "latest_run" not in as_role(INS).get("/api/summary").json()
