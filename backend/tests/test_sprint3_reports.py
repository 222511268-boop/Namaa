"""US21 overview, US22 exports and site report, US23 processing monitoring. Data here is CONSTRUCTED."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    ProcessingRun,
    Role,
    RunKind,
    RunStatus,
    Signal,
    SignalStatus,
    Site,
    Task,
    TaskStatus,
)
from app.services.analysis import analyse_sites
from tests.analysis_helpers import add_observations, history, latest
from tests.conftest import square

DECLINE = [("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]
NORMAL = [("2026-05-05", 0.35), ("2026-05-10", 0.36), ("2026-05-15", 0.35)]


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def world(manager, db, district, users):
    """Five sites in the test district plus one outside it, with signals, tasks and outcomes."""
    def site(name, lon, lat=24.705, size=0.003):
        r = manager.post("/api/sites", json={"name": name, "site_type": "park", "planting_category": "turf",
                                             "geometry": square(lon, lat, size)})
        assert r.status_code == 201, r.text
        return r.json()

    a, b, c = site("Ov Decline A", 46.701), site("Ov Decline B", 46.705), site("Ov Normal C", 46.709)
    d = site("Ov Empty D", 46.713)  # no observations
    small = site("Ov Small E", 46.716, size=0.0004)  # low confidence
    outside = site("Ov Outside F", 46.60, lat=24.60)
    for s, pts in ((a, DECLINE), (b, DECLINE), (c, NORMAL), (outside, DECLINE)):
        add_observations(db, uuid.UUID(s["id"]), history(0.35, 0.03, 0.01, [2025]) + latest(pts))
    analyse_sites(db)
    sigs = {s["site_name"]: s["id"] for s in manager.get("/api/signals").json()}
    due = (date.today() + timedelta(days=3)).isoformat()
    insp = str(users[Role.inspector].id)
    t = manager.post(f"/api/signals/{sigs['Ov Decline A']}/inspection", json={
        "title": "Inspect A", "priority": "high", "due_date": due, "assignee_id": insp}).json()
    assert manager.post(f"/api/signals/{sigs['Ov Decline B']}/confirm", json={}).status_code == 200
    # An overdue task: created normally, then its due date moved into the past directly in the database.
    t2 = manager.post("/api/tasks", json={"site_id": c["id"], "task_type": "maintenance", "title": "Fix valve",
                                          "priority": "low", "due_date": due, "assignee_id": insp}).json()
    db.query(Task).filter(Task.id == uuid.UUID(t2["id"])).update({"due_date": date.today() - timedelta(days=2)})
    db.commit()
    return {"a": a, "b": b, "c": c, "d": d, "small": small, "outside": outside, "task": t, "district": district}


def test_ac_21_1_overview_counts(manager, world, as_role):
    did = world["district"].id
    ov = as_role(Role.viewer).get("/api/overview", params={"district_id": did}).json()
    assert ov["sites_total"] == 5
    c = ov["conditions"]
    assert c["needs_attention"] == 1  # A (under inspection); B was confirmed and closed
    assert c["low_confidence"] == 1 and c["no_satellite_data"] == 1
    assert c["below_range"] == 1 and c["within_range"] == 1
    assert sum(c.values()) == 5
    assert ov["signals"] == {"open": 0, "under_inspection": 1, "dismissed": 0, "closed": 1}
    assert ov["tasks"]["assigned"] == 2 and ov["overdue_tasks"] == 1
    assert ov["outcomes"]["confirmed"] == 1 and ov["outcomes_by_method"]["desk_review"] == 1
    assert ov["confirmation_rate_pct"] is None  # desk review is not field confirmation


def test_ac_21_2_figures_match_underlying_records(manager, world, db):
    ov = manager.get("/api/overview").json()  # all districts, last 90 days
    assert ov["sites_total"] == db.scalar(select(func.count()).select_from(Site).where(Site.status == "active"))
    for st in SignalStatus:
        assert ov["signals"][st.value] == db.scalar(select(func.count()).select_from(Signal).where(Signal.status == st))
    for st in TaskStatus:
        assert ov["tasks"][st.value] == db.scalar(select(func.count()).select_from(Task).where(Task.status == st))
    assert ov["signals"]["open"] == 1  # the site outside the district


def test_ac_21_3_district_and_period_filters(manager, world, db):
    did = world["district"].id
    all_ = manager.get("/api/overview").json()
    one = manager.get("/api/overview", params={"district_id": did}).json()
    assert all_["signals_total"] == 3 and one["signals_total"] == 2
    assert one["filters"]["district_name"] == "Test District"
    # Move every signal's detection date to last year: a period covering only the last 30 days excludes them.
    db.query(Signal).update({"detected_at": datetime.now(UTC) - timedelta(days=400)})
    db.commit()
    recent = manager.get("/api/overview", params={"start": (date.today() - timedelta(days=30)).isoformat()}).json()
    assert recent["signals_total"] == 0
    old = manager.get("/api/overview", params={"start": (date.today() - timedelta(days=500)).isoformat()}).json()
    assert old["signals_total"] == 3
    assert manager.get("/api/overview", params={"start": "2026-06-02", "end": "2026-06-01"}).status_code == 422


def test_overview_permissions(as_role):
    assert as_role(Role.inspector).get("/api/overview").status_code == 403
    for r in (Role.admin, Role.manager, Role.viewer):
        assert as_role(r).get("/api/overview").status_code == 200


def _rows(resp):
    text = resp.content.decode("utf-8-sig")
    lines = text.splitlines()
    meta = [x for x in lines if x.startswith("# ") or x.startswith('"# ')]
    data = list(csv.DictReader(io.StringIO("\n".join(x for x in lines if not (x.startswith("# ") or
                                                                                 x.startswith('"# '))))))
    return meta, data


def test_ac_22_1_csv_exports_follow_filters(manager, world):
    did = world["district"].id
    r = manager.get("/api/exports/sites.csv", params={"district_id": did})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    meta, rows = _rows(r)
    assert len(rows) == 5 and {x["name"] for x in rows} >= {"Ov Decline A", "Ov Small E"}
    assert next(x for x in rows if x["name"] == "Ov Decline A")["condition"] == "needs_attention"
    _, sig_rows = _rows(manager.get("/api/exports/signals.csv", params={"status": "closed"}))
    assert [x["site"] for x in sig_rows] == ["Ov Decline B"] and sig_rows[0]["outcome"] == "confirmed"
    _, task_rows = _rows(manager.get("/api/exports/tasks.csv", params={"status": "open"}))
    assert len(task_rows) == 2 and {x["overdue"] for x in task_rows} == {"yes", "no"}


def test_ac_22_2_exports_include_sources_and_attribution(manager, world):
    for path in ("sites", "signals"):
        meta, _ = _rows(manager.get(f"/api/exports/{path}.csv"))
        joined = " ".join(meta)
        assert "# Source:" in joined and "Filters:" in joined and "Generated:" in joined
    meta, _ = _rows(manager.get("/api/exports/sites.csv"))
    assert any("OpenStreetMap" in m for m in meta) and any("Copernicus Sentinel" in m for m in meta)
    meta, _ = _rows(manager.get("/api/exports/signals.csv"))
    assert any("Copernicus Sentinel" in m for m in meta) and any("Geological Survey" in m for m in meta)


def test_ac_22_3_exports_respect_role_permissions(world, as_role, users):
    viewer, insp = as_role(Role.viewer), as_role(Role.inspector)
    assert viewer.get("/api/exports/sites.csv").status_code == 200
    assert viewer.get("/api/exports/signals.csv").status_code == 403
    assert viewer.get("/api/exports/tasks.csv").status_code == 403
    assert insp.get("/api/exports/signals.csv").status_code == 403
    _, rows = _rows(insp.get("/api/exports/tasks.csv"))
    assert rows and all(x["assignee"] == users[Role.inspector].full_name for x in rows)
    meta, _ = _rows(insp.get("/api/exports/tasks.csv"))
    assert any("own tasks" in m for m in meta)


def test_csv_formula_injection_neutralised(manager, db, world):
    site = db.get(Site, uuid.UUID(world["d"]["id"]))
    site.name = "=HYPERLINK(\"http://x\")"
    db.commit()
    _, rows = _rows(manager.get("/api/exports/sites.csv"))
    assert any(x["name"].startswith("'=") for x in rows)


def test_ac_22_4_printable_site_report_by_role(world, as_role):
    sid = world["a"]["id"]
    m = as_role(Role.manager).get(f"/api/sites/{sid}/report").json()
    assert m["site"]["name"] == "Ov Decline A" and m["condition"] == "needs_attention"
    assert m["signals"] and m["tasks"] and m["water"]["label"] == "Estimate"
    assert any("Copernicus" in a for a in m["attribution"]) and any("Open-Meteo" in a for a in m["attribution"])
    v = as_role(Role.viewer).get(f"/api/sites/{sid}/report").json()
    assert "signals" not in v and "tasks" not in v
    i = as_role(Role.inspector).get(f"/api/sites/{sid}/report").json()
    assert "signals" not in i and len(i["tasks"]) == 1


# ---------------------------------------------------------------- US23


def test_ac_23_1_runs_listed_with_type_time_status_items_errors(as_role, db):
    db.add_all([
        ProcessingRun(kind=RunKind.weather, status=RunStatus.failed, error="The weather service could not be reached",
                      params={}, created_at=datetime.now(UTC) - timedelta(hours=1)),
        ProcessingRun(kind=RunKind.landsat_lst, status=RunStatus.succeeded, params={}, items_written=12,
                      scenes_processed=2, finished_at=datetime.now(UTC)),
    ])
    db.commit()
    runs = as_role(Role.admin).get("/api/processing-runs").json()
    kinds = {r["kind"]: r for r in runs}
    assert kinds["weather"]["error"] and kinds["weather"]["status"] == "failed"
    assert kinds["landsat_lst"]["items_written"] == 12 and kinds["landsat_lst"]["created_at"]


def test_ac_23_2_admin_can_rerun(as_role, db, manager, world):
    admin = as_role(Role.admin)
    old = ProcessingRun(kind=RunKind.sentinel2, status=RunStatus.failed, error="x",
                        params={"start_date": "2026-05-01", "end_date": "2026-05-31", "site_ids": None})
    db.add(old)
    db.commit()
    r = admin.post(f"/api/processing-runs/{old.id}/rerun")
    assert r.status_code == 202, r.text
    new = r.json()
    assert new["kind"] == "sentinel2" and new["status"] == "queued" and new["params"]["start_date"] == "2026-05-01"
    # Only one queued run of a type at a time.
    assert admin.post(f"/api/processing-runs/{old.id}/rerun").status_code == 409
    assert as_role(Role.viewer).post(f"/api/processing-runs/{old.id}/rerun").status_code == 403
    acts = admin.get("/api/activity", params={"action": "run.queued"}).json()["items"]
    assert acts and acts[0]["details"]["rerun_of"] == str(old.id)


def test_new_run_types_can_be_started(manager, world):
    for kind in ("landsat_lst", "weather"):
        r = manager.post("/api/processing-runs", json={"kind": kind, "start_date": "2026-05-01",
                                                       "end_date": "2026-05-31"})
        assert r.status_code == 202 and r.json()["kind"] == kind


def test_ac_23_3_latest_data_date_per_source(as_role, db, world):
    from app.models import LstObservation, WeatherDaily

    sid = uuid.UUID(world["a"]["id"])
    db.add(WeatherDaily(site_id=sid, day=date(2026, 10, 30), et0_mm=5.1, source="open-meteo-archive"))
    db.add(LstObservation(site_id=sid, scene_id="CONSTRUCTED", platform="landsat-9", acquired_on=date(2026, 10, 21),
                          site_c=30, surround_c=33, site_pixels=10, surround_pixels=40, valid_share=1, usable=True))
    db.commit()
    fresh = {f["source"]: f for f in as_role(Role.admin).get("/api/data-freshness").json()}
    assert fresh["sentinel2"]["latest_data_on"] == "2026-05-15"
    assert fresh["weather"]["latest_data_on"] == "2026-10-30"
    assert fresh["landsat_lst"]["latest_data_on"] == "2026-10-21"
    assert set(fresh) == {"sentinel2", "landsat_lst", "weather", "osm_import"}
    assert as_role(Role.viewer).get("/api/data-freshness").status_code == 403


def test_worker_claims_every_worker_kind(db):
    from app.services.processing import claim_next_run, requeue_interrupted_runs

    for kind in (RunKind.weather, RunKind.landsat_lst):
        db.add(ProcessingRun(kind=kind, status=RunStatus.queued, params={}))
        db.commit()
        run = claim_next_run(db)
        assert run is not None and run.kind == kind and run.status == RunStatus.running
    assert requeue_interrupted_runs(db) == 2
