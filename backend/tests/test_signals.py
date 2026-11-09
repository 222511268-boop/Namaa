"""US09-US13 and US16 through the API: baselines, signals, queue, evidence, decisions, outcome, timeline."""

import uuid
from datetime import date, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.models import Role, Signal, SignalDecision, SignalStatus, SiteBaseline, Task, TaskStatus
from app.services.analysis import Obs, analyse_sites
from app.services.imagery import generate_signal_images
from app.services.media import media_path
from app.services.processing import analyse_after_run, claim_next_run, execute_run
from tests.analysis_helpers import add_observations, history, latest
from tests.conftest import square
from tests.satellite_fakes import FakeSource, write_scene

DROP = [("2026-05-05", 0.20), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]
NORMAL = [("2026-05-05", 0.35), ("2026-05-10", 0.36), ("2026-05-15", 0.35)]


def _site(manager, name="Signal Park", lon=46.705, size=0.003, site_type="park"):
    r = manager.post(
        "/api/sites",
        json={"name": name, "site_type": site_type, "planting_category": "turf", "geometry": square(lon, 24.705, size)},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _latest(points):
    return latest(points)


def _seed(db, site_id, latest, level=0.35):
    add_observations(db, uuid.UUID(site_id), history(level, 0.03, 0.01, [2025]) + _latest(latest))


@pytest.fixture
def manager(as_role):
    return as_role(Role.manager)


@pytest.fixture
def inspector_id(users):
    return str(users[Role.inspector].id)


def _task_body(inspector_id, **kw):
    return {
        "title": "Inspect turf condition",
        "instructions": "Check irrigation lines",
        "priority": "high",
        "due_date": (date.today() + timedelta(days=3)).isoformat(),
        "assignee_id": inspector_id,
        **kw,
    }


def _signal_for(db, manager, **site_kw):
    site = _site(manager, **site_kw)
    _seed(db, site["id"], DROP)
    analyse_sites(db)
    return site, db.scalar(select(Signal).where(Signal.site_id == uuid.UUID(site["id"])))


# ---------------------------------------------------------------- baselines and detection


def test_ac_09_2_baselines_stored_with_counts_and_years(manager, db):
    site = _site(manager)
    _seed(db, site["id"], NORMAL)
    analyse_sites(db)
    rows = manager.get(f"/api/sites/{site['id']}/baselines").json()
    assert len(rows) == 12 and all(r["available"] and r["years"] == "2025" and r["n_obs"] >= 8 for r in rows)
    assert all(r["target_year"] == 2026 for r in rows)


def test_ac_09_4_baselines_recalculate_after_processing_run(manager, db, tmp_path):
    site = _site(manager)
    _seed(db, site["id"], NORMAL)
    manager.post("/api/processing-runs", json={"start_date": "2026-05-01", "end_date": "2026-05-30"})
    run = execute_run(db, claim_next_run(db), FakeSource([write_scene(tmp_path, "S2B_RUN")]))
    assert db.scalar(select(func.count()).select_from(SiteBaseline)) == 0
    analyse_after_run(db, run, FakeSource([]))
    assert db.scalar(select(func.count()).select_from(SiteBaseline)) == 12
    assert any("Analysis:" in m for m in run.messages)


def test_ac_10_2_signal_stores_values_and_triggering_observations(manager, db):
    site, sig = _signal_for(db, manager)
    assert sig is not None and sig.status == SignalStatus.open
    assert sig.latest_ndvi == 0.18 and sig.first_obs_on == date(2026, 5, 5) and sig.last_obs_on == date(2026, 5, 15)
    assert sig.deviation == pytest.approx(0.18 - sig.baseline_median) and sig.z_score < -2
    ev = sig.evidence["observations"]
    assert [o["date"] for o in ev] == ["2026-05-05", "2026-05-10", "2026-05-15"]
    assert all(o["observation_id"] for o in ev)


def test_ac_10_3_repeated_detection_updates_instead_of_duplicating(manager, db):
    site, sig = _signal_for(db, manager)
    add_observations(db, uuid.UUID(site["id"]), _latest([("2026-05-20", 0.15)]))
    summary = analyse_sites(db)
    assert summary.signals_created == 0 and summary.signals_updated == 1
    assert db.scalar(select(func.count()).select_from(Signal)) == 1
    db.expire_all()
    assert db.get(Signal, sig.id).latest_ndvi == 0.15


def test_ac_10_4_low_confidence_and_no_baseline_sites_not_evaluated(manager, db):
    small = _site(manager, name="Tiny", size=0.0005)  # ~2,800 m2
    _seed(db, small["id"], DROP)
    young = _site(manager, name="New Park", lon=46.712)
    add_observations(db, uuid.UUID(young["id"]), _latest(DROP))  # no earlier year
    summary = analyse_sites(db)
    assert summary.signals_created == 0
    assert summary.skipped.get("low confidence site") == 1
    assert summary.skipped.get("Baseline not available for the latest observations") == 1


# ---------------------------------------------------------------- queue (US11)


def test_ac_11_1_queue_ordered_by_priority_with_factors(manager, db, as_role):
    _signal_for(db, manager, name="Small Plaza", site_type="plaza", size=0.0008)
    _signal_for(db, manager, name="Big Park", lon=46.712, size=0.006)
    q = manager.get("/api/signals").json()
    assert [s["site_name"] for s in q] == ["Big Park", "Small Plaza"]
    assert q[0]["priority_score"] > q[1]["priority_score"]
    f = q[0]["priority_factors"]
    assert set(f) >= {"severity", "persistence", "size", "site_type"}
    assert q[0]["priority_score"] == pytest.approx(f["severity"] + f["persistence"] + f["size"] + f["site_type"])
    assert as_role(Role.admin).get("/api/signals").status_code == 200


def test_ac_11_3_filters_and_empty_result(manager, db, district):
    _signal_for(db, manager)  # inside the test district
    assert len(manager.get("/api/signals", params={"district_id": district.id}).json()) == 1
    assert manager.get("/api/signals", params={"district_id": district.id + 999}).json() == []
    assert manager.get("/api/signals", params={"status": "dismissed"}).json() == []


@pytest.mark.parametrize("role", [Role.inspector, Role.viewer])
def test_ac_13_1_queue_and_decisions_refused_for_other_roles(as_role, manager, db, role):
    _, sig = _signal_for(db, manager)
    c = as_role(role)
    assert c.get("/api/signals").status_code == 403
    assert c.get(f"/api/signals/{sig.id}").status_code == 403
    assert c.post(f"/api/signals/{sig.id}/confirm", json={}).status_code == 403


def test_ac_13_1_admin_reads_but_cannot_decide(as_role, manager, db):
    _, sig = _signal_for(db, manager)
    admin = as_role(Role.admin)
    assert admin.get(f"/api/signals/{sig.id}").status_code == 200
    assert admin.post(f"/api/signals/{sig.id}/dismiss", json={"reason": "x"}).status_code == 403


# ---------------------------------------------------------------- evidence (US12)


def test_ac_12_3_evidence_matches_stored_observations(manager, db):
    _, sig = _signal_for(db, manager)
    d = manager.get(f"/api/signals/{sig.id}").json()
    assert d["latest_ndvi"] == 0.18 and d["evidence"]["observations"][-1]["ndvi"] == 0.18
    assert d["after_image"]["date"] == "2026-05-15" and d["after_image"]["url"] is None  # no image yet
    assert d["before_image"]["date"].startswith("2025-05")  # same season, earlier year
    assert d["attribution"].startswith("Contains modified Copernicus Sentinel data")


def test_ac_12_2_image_chips_created_and_served(manager, db, tmp_path):
    site = _site(manager)
    before = write_scene(tmp_path / "b", "S2B_BEFORE", when=datetime(2025, 5, 14, 7, 26))
    after = write_scene(tmp_path / "a", "S2B_AFTER", when=datetime(2026, 5, 15, 7, 26))
    series = history(0.35, 0.03, 0.01, [2025]) + _latest(DROP)
    # Point the closest same-season observations at the fake scenes.
    series = [Obs(o.id, o.day, o.ndvi, "S2B_BEFORE" if o.day == date(2025, 5, 16) else o.scene_id) for o in series]
    series[-1] = Obs(series[-1].id, series[-1].day, series[-1].ndvi, "S2B_AFTER")
    add_observations(db, uuid.UUID(site["id"]), series)
    summary = analyse_sites(db)
    assert generate_signal_images(db, FakeSource([before, after]), summary.changed_signal_ids) == 2
    d = manager.get(f"/api/signals/{summary.changed_signal_ids[0]}").json()
    for key in ("before_image", "after_image"):
        url = d[key]["url"]
        assert url.startswith("/api/media/chips/")
        r = manager.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        img = Image.open(media_path("chips", url.rsplit("/", 1)[1]))
        assert max(img.size) == 384


def test_ac_12_2_image_failure_does_not_block_signal(manager, db):
    _, sig = _signal_for(db, manager)
    assert generate_signal_images(db, FakeSource([]), [sig.id]) == 0
    db.expire_all()
    assert db.get(Signal, sig.id).status == SignalStatus.open


def test_media_requires_sign_in_and_rejects_paths(client, manager):
    assert client.get("/api/media/chips/" + "a" * 32 + ".png").status_code == 401
    assert manager.get("/api/media/chips/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert manager.get("/api/media/other/" + "a" * 32 + ".png").status_code == 404


# ---------------------------------------------------------------- decisions (US13)


def test_ac_13_2_dismiss_requires_reason_and_records_history(manager, db):
    _, sig = _signal_for(db, manager)
    r = manager.post(f"/api/signals/{sig.id}/dismiss", json={"reason": "   "})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "reason"
    r = manager.post(f"/api/signals/{sig.id}/dismiss", json={"reason": "Replanting works under way"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    h = r.json()["decisions"]
    assert h[-1]["decision"] == "dismiss" and h[-1]["reason"] == "Replanting works under way"
    assert h[-1]["user_name"] == "Test Manager" and h[-1]["created_at"]


def test_ac_13_4_dismissed_signal_reopens_only_on_new_observations(manager, db):
    site, sig = _signal_for(db, manager)
    manager.post(f"/api/signals/{sig.id}/dismiss", json={"reason": "Known works"})
    assert analyse_sites(db).signals_reopened == 0  # same observations: stays dismissed
    add_observations(db, uuid.UUID(site["id"]), _latest([("2026-05-20", 0.18), ("2026-05-25", 0.17)]))
    assert analyse_sites(db).signals_reopened == 0  # window still includes a reviewed observation
    add_observations(db, uuid.UUID(site["id"]), _latest([("2026-05-30", 0.17)]))
    assert analyse_sites(db).signals_reopened == 1
    d = manager.get(f"/api/signals/{sig.id}").json()
    assert d["status"] == "open" and d["reopened_count"] == 1 and d["decisions"][-1]["decision"] == "reopened"


def test_ac_13_5_invalid_transitions_rejected(manager, db, inspector_id):
    _, sig = _signal_for(db, manager)
    assert manager.post(f"/api/signals/{sig.id}/outcome", json={"outcome": "confirmed"}).status_code == 409
    assert manager.post(f"/api/signals/{sig.id}/confirm", json={"reason": "Visible on imagery"}).status_code == 200
    assert manager.post(f"/api/signals/{sig.id}/dismiss", json={"reason": "late"}).status_code == 409
    assert manager.post(f"/api/signals/{sig.id}/inspection", json=_task_body(inspector_id)).status_code == 409
    d = manager.get(f"/api/signals/{sig.id}").json()
    assert d["status"] == "closed" and d["outcome"] == "confirmed" and d["outcome_method"] == "desk_review"


# ---------------------------------------------------------------- inspection loop (US14, US16)


def test_ac_14_4_and_16_1_inspection_loop(manager, db, as_role, inspector_id):
    site, sig = _signal_for(db, manager)
    r = manager.post(f"/api/signals/{sig.id}/inspection", json=_task_body(inspector_id))
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["signal_id"] == str(sig.id) and task["task_type"] == "inspection" and task["status"] == "assigned"
    assert manager.get(f"/api/signals/{sig.id}").json()["status"] == "under_inspection"
    # Outcome is not allowed before the inspection is completed.
    assert manager.post(f"/api/signals/{sig.id}/outcome", json={"outcome": "confirmed"}).status_code == 409

    insp = as_role(Role.inspector)
    insp.put(
        f"/api/tasks/{task['id']}/findings",
        json={"visit_date": date.today().isoformat(), "condition": "stressed", "notes": "Dry patches near pump"},
    )
    assert insp.post(f"/api/tasks/{task['id']}/complete").json()["status"] == "completed"

    r = manager.post(f"/api/signals/{sig.id}/outcome", json={"outcome": "confirmed", "note": "Pump failure"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "closed" and d["outcome"] == "confirmed" and d["outcome_method"] == "field_inspection"

    # AC-16.2 timeline in time order.
    tl = manager.get(f"/api/sites/{site['id']}/timeline").json()
    kinds = [e["kind"] for e in tl["events"]]
    assert kinds == [
        "signal_detected",
        "task_created",
        "decision_send_for_inspection",
        "task_completed",
        "decision_record_outcome",
    ] or kinds == [
        "signal_detected",
        "decision_send_for_inspection",
        "task_created",
        "task_completed",
        "decision_record_outcome",
    ]
    assert [e["at"] for e in tl["events"]] == sorted(e["at"] for e in tl["events"])
    assert tl["active_signal_id"] is None
    assert as_role(Role.viewer).get(f"/api/sites/{site['id']}/timeline").status_code == 200


def test_ac_14_5_cancelling_inspection_reopens_signal(manager, db, inspector_id):
    _, sig = _signal_for(db, manager)
    task = manager.post(f"/api/signals/{sig.id}/inspection", json=_task_body(inspector_id)).json()
    r = manager.post(f"/api/tasks/{task['id']}/cancel", json={"reason": "Inspector unavailable"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    d = manager.get(f"/api/signals/{sig.id}").json()
    assert d["status"] == "open" and d["decisions"][-1]["decision"] == "inspection_cancelled"
    assert db.scalar(select(func.count()).select_from(SignalDecision)) == 2
    assert db.scalar(select(Task.status)) == TaskStatus.cancelled


def test_unchanged_signal_does_not_regenerate_images(manager, db, tmp_path):
    site = _site(manager)
    after = write_scene(tmp_path / "a", "S2B_AFTER2", when=datetime(2026, 5, 15, 7, 26))
    series = history(0.35, 0.03, 0.01, [2025]) + _latest(DROP)
    series[-1] = Obs(series[-1].id, series[-1].day, series[-1].ndvi, "S2B_AFTER2")
    add_observations(db, uuid.UUID(site["id"]), series)
    first = analyse_sites(db)
    assert generate_signal_images(db, FakeSource([after]), first.changed_signal_ids) == 1
    again = analyse_sites(db)  # same observations: the signal is updated but the image is still current
    assert generate_signal_images(db, FakeSource([after]), again.changed_signal_ids) == 0
