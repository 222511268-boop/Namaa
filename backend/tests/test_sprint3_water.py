"""US17-US18: weather-based water-demand estimates and irrigation schedule comparison.

Weather responses are CONSTRUCTED (respx mocks of the Open-Meteo API); no real weather is claimed.
"""

import uuid
from datetime import date, timedelta

import httpx
import pytest
import respx

from app.models import ProcessingRun, Role, RunKind, RunStatus, WeatherDaily
from app.services import weather
from app.services.water import daily_demand_l, scheduled_litres
from tests.conftest import square

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def site(manager):
    # 0.002 degrees square: about 4.5 ha
    r = manager.post("/api/sites", json={"name": "Water Park", "site_type": "park", "planting_category": "turf",
                                         "geometry": square(46.705, 24.705, 0.002)})
    assert r.status_code == 201, r.text
    return r.json()


def _daily(days: list[date], et0: list[float | None]) -> dict:
    return {"daily": {"time": [d.isoformat() for d in days], "et0_fao_evapotranspiration": et0,
                      "temperature_2m_max": [40.0] * len(days), "temperature_2m_min": [28.0] * len(days),
                      "precipitation_sum": [0.0] * len(days)}}


def _store(db, site_id, start: date, values: list[float]):
    for i, v in enumerate(values):
        db.add(WeatherDaily(site_id=uuid.UUID(site_id), day=start + timedelta(days=i), et0_mm=v, tmax_c=40,
                            tmin_c=28, precip_mm=0, source="open-meteo-archive"))
    db.commit()


def test_demand_formula():
    # 6 mm/day x 0.6 x 1000 m2 = 3600 litres
    assert daily_demand_l(6.0, 0.6, 1000) == pytest.approx(3600)


def test_ac_17_1_demand_from_et0_plant_factor_and_area(manager, site, db):
    start = date(2026, 6, 1)
    _store(db, site["id"], start, [8.0, 7.0, 9.0])
    r = manager.get(f"/api/sites/{site['id']}/water", params={"start": "2026-06-01", "end": "2026-06-03"})
    assert r.status_code == 200, r.text
    w = r.json()
    area = site["area_m2"]
    assert w["inputs"]["plant_factor"] == 0.6 and w["inputs"]["plant_category"] == "turf"
    assert w["inputs"]["irrigated_area_m2"] == pytest.approx(round(area, 1))
    assert [d["demand_l"] for d in w["daily"]] == [round(v * 0.6 * area) for v in (8.0, 7.0, 9.0)]
    assert w["totals"]["demand_m3"] == pytest.approx(round(24.0 * 0.6 * area / 1000, 1))
    assert w["totals"]["et0_mm"] == 24.0


def test_ac_17_2_formula_inputs_source_and_estimate_label(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [8.0])
    w = manager.get(f"/api/sites/{site['id']}/water").json()
    assert w["label"] == "Estimate"
    assert "ET0" in w["formula"] and "plant factor" in w["formula"] and "irrigated area" in w["formula"]
    assert "Open-Meteo" in w["source"] and "CC BY 4.0" in w["source"]
    assert "outside KSA" in w["inputs"]["plant_factor_note"]


def test_irrigated_area_used_when_entered_and_validated(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [10.0])
    body = {"name": "Water Park", "site_type": "park", "planting_category": "turf"}
    too_big = manager.put(f"/api/sites/{site['id']}", json=body | {"irrigated_area_m2": site["area_m2"] * 2})
    assert too_big.status_code == 422 and "cannot be larger" in too_big.text
    assert manager.put(f"/api/sites/{site['id']}", json=body | {"irrigated_area_m2": 1000}).status_code == 200
    w = manager.get(f"/api/sites/{site['id']}/water", params={"start": "2026-06-01", "end": "2026-06-01"}).json()
    assert w["inputs"]["irrigated_area_source"] == "user-entered"
    assert w["daily"][0]["demand_l"] == 6000  # 10 mm x 0.6 x 1000 m2


def test_plant_factor_is_adjustable_and_used(manager, site, db, as_role):
    _store(db, site["id"], date(2026, 6, 1), [10.0])
    r = manager.put("/api/plant-factors/turf", json={"factor": 0.7, "source_note": "Local trial value (assumption)."})
    assert r.status_code == 200 and r.json()["factor"] == 0.7
    assert as_role(Role.viewer).put("/api/plant-factors/turf", json={"factor": 0.5, "source_note": "x y z"}
                                    ).status_code == 403
    assert manager.put("/api/plant-factors/turf", json={"factor": 3, "source_note": "too high"}).status_code == 422
    w = manager.get(f"/api/sites/{site['id']}/water", params={"start": "2026-06-01", "end": "2026-06-01"}).json()
    assert w["inputs"]["plant_factor"] == 0.7


@respx.mock
def test_ac_17_1_weather_run_stores_archive_and_recent_values(manager, site, db):
    today = weather.riyadh_today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=19)
    days = [start + timedelta(days=i) for i in range(20)]
    # The archive lacks the last 3 days; the forecast API fills them.
    respx.get(ARCHIVE).mock(return_value=httpx.Response(200, json=_daily(days, [5.0] * 17 + [None] * 3)))
    recent = [d for d in days if d >= today - timedelta(days=weather.RECENT_DAYS)]
    respx.get(FORECAST).mock(return_value=httpx.Response(200, json=_daily(recent, [6.0] * len(recent))))
    run = ProcessingRun(kind=RunKind.weather, status=RunStatus.running,
                        params={"start_date": start.isoformat(), "end_date": end.isoformat()})
    db.add(run)
    db.commit()
    weather.execute_weather_run(db, run)
    assert run.status == RunStatus.succeeded, run.error
    rows = db.query(WeatherDaily).order_by(WeatherDaily.day).all()
    assert len(rows) == 20 and run.items_written == 20
    assert {r.source for r in rows[-3:]} == {"open-meteo-forecast"} and rows[-1].et0_mm == 6.0
    assert rows[0].source == "open-meteo-archive" and rows[0].et0_mm == 5.0
    # The request asked for the Riyadh time zone and the FAO-56 reference evapotranspiration variable.
    req = respx.calls[0].request
    assert "et0_fao_evapotranspiration" in str(req.url) and "Asia%2FRiyadh" in str(req.url)


@respx.mock
def test_ac_17_3_weather_failure_shows_last_stored_values_with_date(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [8.0, 8.5])
    respx.get(ARCHIVE).mock(return_value=httpx.Response(503))
    run = ProcessingRun(kind=RunKind.weather, status=RunStatus.running,
                        params={"start_date": "2026-06-01", "end_date": "2026-06-10"})
    db.add(run)
    db.commit()
    weather.execute_weather_run(db, run)
    assert run.status == RunStatus.failed and "could not be reached" in run.error
    w = manager.get(f"/api/sites/{site['id']}/water").json()
    assert w["latest_weather_on"] == "2026-06-02"
    assert "showing stored values up to 2026-06-02" in w["notice"]
    assert len(w["daily"]) == 2  # stored values are kept and still shown


def test_scheduled_litres_by_weekday_and_range():
    class S:
        start_date, end_date, weekdays, litres_per_day = date(2026, 6, 1), date(2026, 6, 30), [1, 3, 5], 1000.0

    assert scheduled_litres([S], date(2026, 6, 1)) == 1000  # Monday
    assert scheduled_litres([S], date(2026, 6, 2)) == 0  # Tuesday: covered, no watering
    assert scheduled_litres([S], date(2026, 7, 1)) is None  # outside the schedule


def test_ac_18_1_schedule_validation(manager, site):
    url = f"/api/sites/{site['id']}/schedules"
    good = {"start_date": "2026-06-01", "end_date": "2026-06-30", "weekdays": [1, 3, 5], "litres_per_day": 20000}
    cases = [
        ({"end_date": "2026-05-01"}, "end date"),
        ({"weekdays": []}, "weekdays"),
        ({"weekdays": [1, 1]}, "distinct"),
        ({"weekdays": [8]}, "distinct"),
        ({"litres_per_day": 0}, "litres_per_day"),
        ({"litres_per_day": site["area_m2"] * 101}, "more than 100 mm"),
        ({"start_date": "2010-01-01", "end_date": None}, "2015"),
    ]
    for change, msg in cases:
        r = manager.post(url, json=good | change)
        assert r.status_code == 422 and msg in r.text, (change, r.text)
    assert manager.post(url, json=good).status_code == 201
    overlap = manager.post(url, json=good | {"start_date": "2026-06-15", "end_date": None})
    assert overlap.status_code == 422 and "overlaps" in overlap.text


def test_ac_18_2_comparison_for_selected_period(manager, site, db):
    start = date(2026, 6, 1)  # Monday
    _store(db, site["id"], start, [10.0] * 7)
    area = site["area_m2"]
    r = manager.post(f"/api/sites/{site['id']}/schedules", json={
        "start_date": "2026-06-01", "weekdays": [1, 3, 5], "litres_per_day": 50000})
    assert r.status_code == 201, r.text
    w = manager.get(f"/api/sites/{site['id']}/water", params={"start": "2026-06-01", "end": "2026-06-07"}).json()
    c = w["comparison"]
    demand = sum(round(10 * 0.6 * area) for _ in range(7))
    assert c["days_compared"] == 7
    assert c["scheduled_m3"] == 150.0  # Mon, Wed, Fri x 50 000 litres
    assert c["demand_m3"] == pytest.approx(round(demand / 1000, 1))
    assert c["difference_m3"] == pytest.approx(round((150000 - demand) / 1000, 1))
    assert "user-entered" in c["label"]
    # A different period gives a different comparison.
    w2 = manager.get(f"/api/sites/{site['id']}/water", params={"start": "2026-06-01", "end": "2026-06-02"}).json()
    assert w2["comparison"]["days_compared"] == 2 and w2["comparison"]["scheduled_m3"] == 50.0


def test_ac_18_3_sites_without_schedule_show_demand_only(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [9.0])
    w = manager.get(f"/api/sites/{site['id']}/water").json()
    assert w["has_schedule"] is False and w["comparison"] is None
    assert w["daily"][0]["scheduled_l"] is None and w["totals"]["demand_m3"] > 0


def test_schedule_edit_delete_permissions_and_audit(manager, site, as_role):
    created = manager.post(f"/api/sites/{site['id']}/schedules", json={
        "start_date": "2026-06-01", "weekdays": [2], "litres_per_day": 1000}).json()
    viewer = as_role(Role.viewer)
    assert viewer.post(f"/api/sites/{site['id']}/schedules", json={
        "start_date": "2026-08-01", "weekdays": [2], "litres_per_day": 1000}).status_code == 403
    assert viewer.get(f"/api/sites/{site['id']}/schedules").status_code == 200
    upd = manager.put(f"/api/schedules/{created['id']}", json={
        "start_date": "2026-06-01", "weekdays": [2, 4], "litres_per_day": 1500})
    assert upd.status_code == 200 and upd.json()["weekdays"] == [2, 4]
    assert manager.delete(f"/api/schedules/{created['id']}").status_code == 204
    items = as_role(Role.admin).get("/api/activity", params={"category": "schedule"}).json()["items"]
    acts = [e["action"] for e in items]
    assert sorted(acts) == ["schedule.created", "schedule.deleted", "schedule.updated"]


def test_weather_due_logic(db, site):
    assert weather.weather_due(db) is True
    run = weather.queue_weather_run(db)
    assert weather.weather_due(db) is False  # a run is pending
    run.status = RunStatus.succeeded
    db.commit()
    assert weather.weather_due(db) is False  # fresh


def test_empty_selected_weather_period_is_explicit_even_when_other_weather_exists(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [8.0])
    w = manager.get(f"/api/sites/{site['id']}/water?start=2015-01-01&end=2015-01-02").json()
    assert w["period"]["days_with_data"] == 0
    assert w["totals"]["mean_daily_demand_m3"] is None
    assert "selected period" in w["notice"] and "unavailable" in w["notice"]
    assert w["latest_weather_on"] == "2026-06-01"


def test_weather_rows_without_et0_do_not_become_zero_demand(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [8.0])
    db.query(WeatherDaily).filter_by(site_id=uuid.UUID(site["id"])).one().et0_mm = None
    db.commit()
    w = manager.get(f"/api/sites/{site['id']}/water?start=2026-06-01&end=2026-06-01").json()
    assert w["daily"][0]["demand_l"] is None
    assert w["period"]["days_with_data"] == 0
    assert w["totals"]["mean_daily_demand_m3"] is None
    assert "unavailable" in w["notice"]


def test_genuine_zero_et0_remains_an_available_zero_estimate(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [0.0])
    w = manager.get(f"/api/sites/{site['id']}/water?start=2026-06-01&end=2026-06-01").json()
    assert w["period"]["days_with_data"] == 1
    assert w["totals"]["demand_m3"] == 0
    assert w["totals"]["mean_daily_demand_m3"] == 0
    assert w["notice"] is None


def test_daily_mean_uses_only_days_with_et0(manager, site, db):
    _store(db, site["id"], date(2026, 6, 1), [8.0, 7.0])
    db.query(WeatherDaily).filter_by(site_id=uuid.UUID(site["id"]), day=date(2026, 6, 2)).one().et0_mm = None
    db.commit()
    w = manager.get(f"/api/sites/{site['id']}/water?start=2026-06-01&end=2026-06-02").json()
    assert w["period"]["days_with_data"] == 1
    assert w["totals"]["mean_daily_demand_m3"] == pytest.approx(round(8 * 0.6 * site["area_m2"] / 1000, 2))
