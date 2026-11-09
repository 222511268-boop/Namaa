"""US04 Import green spaces: AC-04.1 to AC-04.5.

Overpass responses are mocked. `CONSTRUCTED` is a hand-built response (not real OSM data) covering each
edge case; `overpass_parks_al_rawdah.json` is a real response recorded from the Overpass API.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon, box

from app.config import get_settings
from app.models import District, Role, Site

FIXTURES = Path(__file__).parent / "fixtures"


def _ring(x0, y0, d=0.001):
    return [
        {"lat": y0, "lon": x0},
        {"lat": y0, "lon": x0 + d},
        {"lat": y0 + d, "lon": x0 + d},
        {"lat": y0 + d, "lon": x0},
        {"lat": y0, "lon": x0},
    ]


CONSTRUCTED = {
    "elements": [
        {
            "type": "way",
            "id": 1,
            "tags": {"leisure": "park", "name": "Named Park", "name:ar": "حديقة مسماة"},
            "geometry": _ring(46.701, 24.701),
        },
        {"type": "way", "id": 2, "tags": {"leisure": "park"}, "geometry": _ring(46.703, 24.703)},
        {
            "type": "way",
            "id": 3,
            "tags": {"leisure": "park", "name": "Open Way"},
            "geometry": _ring(46.705, 24.705)[:-1],
        },
        {
            "type": "way",
            "id": 4,
            "tags": {"leisure": "park", "name": "Bow Tie"},
            "geometry": [
                {"lat": 24.707, "lon": 46.707},
                {"lat": 24.708, "lon": 46.708},
                {"lat": 24.707, "lon": 46.708},
                {"lat": 24.708, "lon": 46.707},
                {"lat": 24.707, "lon": 46.707},
            ],
        },
        {
            "type": "relation",
            "id": 5,
            "tags": {"leisure": "park", "type": "multipolygon", "name": "Ring Park"},
            "members": [
                {"type": "way", "role": "outer", "geometry": _ring(46.710, 24.710, 0.004)},
                {"type": "way", "role": "inner", "geometry": _ring(46.711, 24.711, 0.001)},
            ],
        },
        # In the query bounding box but in a neighbouring district: ignored entirely.
        {
            "type": "way",
            "id": 6,
            "tags": {"leisure": "park", "name": "Neighbour Park"},
            "geometry": _ring(46.725, 24.705),
        },
    ]
}


@pytest.fixture(autouse=True)
def fast_overpass(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "overpass_fallback_urls", ["https://fallback.example/api/interpreter"])
    monkeypatch.setattr(s, "overpass_retry_delay_s", 0)


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@respx.mock
def test_ac_04_1_and_04_3_and_04_5_constructed_cases(manager, district, db):
    respx.post(get_settings().overpass_url).mock(return_value=httpx.Response(200, json=CONSTRUCTED))
    r = manager.post("/api/imports/osm", json={"district_id": district.id})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["features_found"] == 5 and res["created"] == 3 and res["already_imported"] == 0
    reasons = {s["osm_ref"]: s["reason"] for s in res["skipped"]}
    assert reasons == {"way/3": "Not a closed area (open way)", "way/4": "Invalid geometry (self-intersecting)"}

    sites = {s.source_ref: s for s in db.query(Site).all()}
    assert set(sites) == {"way/1", "way/2", "relation/5"}
    named, unnamed, ring = sites["way/1"], sites["way/2"], sites["relation/5"]
    assert named.name == "Named Park" and named.name_ar == "حديقة مسماة"
    assert unnamed.name == "Unnamed park (OSM way 2)"  # AC-04.5
    assert all(s.needs_review and s.planting_category.value == "unknown" for s in sites.values())
    assert all(s.district_id == district.id and s.source.value == "osm" for s in sites.values())
    # Relation with an inner ring: 16 cells minus 1 hole -> 15/16 of the outer area.
    assert ring.area_m2 == pytest.approx(15 * named.area_m2, rel=0.01)
    detail = manager.get(f"/api/sites/{named.id}").json()
    assert detail["source_attribution"] == "© OpenStreetMap contributors (ODbL)"


@respx.mock
def test_ac_04_2_repeat_import_creates_no_duplicates(manager, district, db):
    respx.post(get_settings().overpass_url).mock(return_value=httpx.Response(200, json=CONSTRUCTED))
    manager.post("/api/imports/osm", json={"district_id": district.id})
    again = manager.post("/api/imports/osm", json={"district_id": district.id}).json()
    assert again["created"] == 0 and again["already_imported"] == 3
    assert db.query(Site).count() == 3


@respx.mock
def test_ac_04_2_import_does_not_overwrite_manager_edits(manager, district, db):
    respx.post(get_settings().overpass_url).mock(return_value=httpx.Response(200, json=CONSTRUCTED))
    manager.post("/api/imports/osm", json={"district_id": district.id})
    site = db.query(Site).filter_by(source_ref="way/1").one()
    manager.put(f"/api/sites/{site.id}", json={"name": "Edited", "site_type": "park", "planting_category": "trees"})
    manager.post("/api/imports/osm", json={"district_id": district.id})
    db.expire_all()
    assert db.get(Site, site.id).name == "Edited"


@respx.mock
def test_ac_04_3_outside_pilot_area_skipped(manager, db):
    edge = District(
        osm_id=990002,
        name_en="Edge District",
        geom=from_shape(MultiPolygon([box(46.44, 24.60, 46.46, 24.62)]), srid=4326),
    )
    db.add(edge)
    db.commit()
    data = {
        "elements": [{"type": "way", "id": 7, "tags": {"leisure": "park"}, "geometry": _ring(46.4485, 24.61, 0.002)}]
    }
    respx.post(get_settings().overpass_url).mock(return_value=httpx.Response(200, json=data))
    res = manager.post("/api/imports/osm", json={"district_id": edge.id}).json()
    assert res["created"] == 0 and res["skipped"][0]["reason"] == "Outside the pilot area"


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502),
        httpx.Response(429),
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"elements": [], "remark": 'runtime error: Query timed out in "query"'}),
    ],
    ids=["bad-gateway", "rate-limited", "not-json", "partial-result"],
)
def test_ac_04_4_overpass_failure_creates_nothing(manager, district, db, response):
    respx.post(get_settings().overpass_url).mock(return_value=response)
    respx.post("https://fallback.example/api/interpreter").mock(return_value=response)
    r = manager.post("/api/imports/osm", json={"district_id": district.id})
    assert r.status_code == 502
    assert "OpenStreetMap" in r.json()["detail"]
    assert db.query(Site).count() == 0
    run = manager.get("/api/processing-runs").json()[0]
    assert run["kind"] == "osm_import" and run["status"] == "failed" and run["error"]


@respx.mock
def test_transient_failure_retried_then_fallback_used(manager, district, db):
    primary = respx.post(get_settings().overpass_url).mock(return_value=httpx.Response(502))
    fallback = respx.post("https://fallback.example/api/interpreter").mock(
        return_value=httpx.Response(200, json=CONSTRUCTED)
    )
    r = manager.post("/api/imports/osm", json={"district_id": district.id})
    assert r.status_code == 200 and r.json()["created"] == 3
    assert primary.call_count == 2 and fallback.call_count == 1


def test_unknown_district_404(manager):
    assert manager.post("/api/imports/osm", json={"district_id": 424242}).status_code == 404


@pytest.mark.skipif(not (FIXTURES / "overpass_parks_al_rawdah.json").exists(), reason="real fixture not recorded")
@respx.mock
def test_ac_04_1_real_recorded_response(manager, db):
    """Real OSM data recorded from the Overpass API for Al Rawdah District, Riyadh."""
    districts = json.loads(
        (Path(__file__).parents[1] / "data" / "riyadh_districts.geojson").read_text(encoding="utf-8")
    )
    feat = next(f for f in districts["features"] if f["properties"]["osm_id"] == 13253979)
    from shapely.geometry import shape

    d = District(
        osm_id=13253979,
        name_en="Al Rawdah District",
        geom=from_shape(MultiPolygon(list(shape(feat["geometry"]).geoms)), srid=4326),
    )
    db.add(d)
    db.commit()
    data = json.loads((FIXTURES / "overpass_parks_al_rawdah.json").read_text(encoding="utf-8"))
    respx.post(get_settings().overpass_url).mock(return_value=httpx.Response(200, json=data))
    res = manager.post("/api/imports/osm", json={"district_id": d.id}).json()
    assert res["created"] > 0
    assert res["created"] + res["already_imported"] + len(res["skipped"]) == res["features_found"]
    assert db.query(Site).count() == res["created"]
