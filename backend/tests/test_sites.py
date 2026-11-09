"""US05 Register and edit a green space (AC-05.x) and US06 search/filter API (AC-06.2, AC-06.3)."""

import pytest

from app.models import Role
from tests.conftest import square


def body(**kw):
    b = {
        "name": "Al Test Park",
        "name_ar": "حديقة الاختبار",
        "site_type": "park",
        "planting_category": "turf",
        "geometry": square(46.705, 24.705),
    }
    b.update(kw)
    return b


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


def test_ac_05_1_create_site_with_calculated_area_and_district(manager, district):
    r = manager.post("/api/sites", json=body())
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["area_m2"] == pytest.approx(11_200, rel=0.02)
    assert s["district_id"] == district.id and s["district_name"] == "Test District"
    assert s["source"] == "manual" and s["status"] == "active" and s["needs_review"] is False
    assert manager.get(f"/api/sites/{s['id']}").json()["name_ar"] == "حديقة الاختبار"


def test_ac_05_2_invalid_boundary_rejected_on_geometry_field(manager):
    r = manager.post("/api/sites", json=body(geometry=square(45.0, 24.0)))
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["body", "geometry"]
    assert "pilot area" in r.json()["detail"][0]["msg"]


@pytest.mark.parametrize(
    "override, field",
    [
        ({"name": "   "}, "name"),
        ({"name": "x" * 121}, "name"),
        ({"site_type": "forest"}, "site_type"),
        ({"planting_category": "cactus"}, "planting_category"),
        ({"planting_category": "unknown"}, "planting_category"),
    ],
)
def test_ac_05_3_attribute_validation(manager, override, field):
    r = manager.post("/api/sites", json=body(**override))
    assert r.status_code == 422
    assert any(e["loc"][-1] == field for e in r.json()["detail"]), r.json()


def test_ac_05_4_edit_persists_and_recalculates(manager, district):
    sid = manager.post("/api/sites", json=body()).json()["id"]
    outside_district = square(46.80, 24.80, 0.002)
    r = manager.put(
        f"/api/sites/{sid}", json=body(name="Renamed Park", planting_category="trees", geometry=outside_district)
    )
    assert r.status_code == 200, r.text
    again = manager.get(f"/api/sites/{sid}").json()
    assert again["name"] == "Renamed Park" and again["planting_category"] == "trees"
    assert again["area_m2"] == pytest.approx(4 * 11_200, rel=0.02)
    assert again["district_id"] is None  # moved outside the test district


def test_ac_05_4_edit_without_geometry_keeps_boundary(manager):
    created = manager.post("/api/sites", json=body()).json()
    b = body(name="Same Shape")
    del b["geometry"]
    r = manager.put(f"/api/sites/{created['id']}", json=b)
    assert r.status_code == 200 and r.json()["area_m2"] == created["area_m2"]


def test_ac_05_5_small_sites_flagged_low_confidence(manager):
    small = manager.post("/api/sites", json=body(geometry=square(46.705, 24.705, 0.0005))).json()  # ~2,800 m2
    large = manager.post("/api/sites", json=body(name="Large", geometry=square(46.71, 24.71, 0.001))).json()
    assert small["low_confidence"] is True and small["area_m2"] < 5000
    assert large["low_confidence"] is False


def test_ac_05_6_deactivated_sites_hidden_by_default(manager):
    sid = manager.post("/api/sites", json=body()).json()["id"]
    assert manager.patch(f"/api/sites/{sid}/status", json={"status": "inactive"}).status_code == 200
    assert manager.get("/api/sites").json() == []
    listed = manager.get("/api/sites", params={"include_inactive": True}).json()
    assert [s["id"] for s in listed] == [sid] and listed[0]["status"] == "inactive"
    assert manager.get("/api/sites/geojson").json()["features"] == []


def test_unknown_site_returns_404(manager):
    assert manager.get("/api/sites/00000000-0000-0000-0000-000000000000").status_code == 404


def _seed(manager):
    manager.post(
        "/api/sites",
        json=body(name="King Abdullah Park", name_ar="حديقة الملك عبدالله", geometry=square(46.701, 24.701)),
    )
    manager.post(
        "/api/sites",
        json=body(name="Olaya Garden", name_ar="حديقة العليا", site_type="garden", geometry=square(46.703, 24.703)),
    )
    manager.post(
        "/api/sites", json=body(name="Northern Median", name_ar=None, site_type="median", geometry=square(46.85, 24.85))
    )


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"q": "king"}, {"King Abdullah Park"}),  # partial, case-insensitive English
        ({"q": "العليا"}, {"Olaya Garden"}),  # Arabic
        ({"q": "100%"}, set()),  # wildcard characters are literal
        ({"site_type": "garden"}, {"Olaya Garden"}),
    ],
)
def test_ac_06_2_search(manager, district, params, expected):
    _seed(manager)
    assert {s["name"] for s in manager.get("/api/sites", params=params).json()} == expected


def test_ac_06_3_filters_combine_with_and(manager, district):
    _seed(manager)
    in_district = {s["name"] for s in manager.get("/api/sites", params={"district_id": district.id}).json()}
    assert in_district == {"King Abdullah Park", "Olaya Garden"}
    both = manager.get("/api/sites", params={"district_id": district.id, "site_type": "median"}).json()
    assert both == []
    geo = manager.get("/api/sites/geojson", params={"district_id": district.id, "site_type": "park"}).json()
    assert [f["properties"]["name"] for f in geo["features"]] == ["King Abdullah Park"]


def test_districts_listed_with_site_counts(manager, district):
    _seed(manager)
    d = manager.get("/api/districts").json()
    assert d == [{"id": district.id, "name_en": "Test District", "name_ar": "حي الاختبار", "site_count": 2}]
