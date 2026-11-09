"""Regressions for Sprint 3 integration and evidence correctness; all observations are constructed."""

import uuid
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.models import Role, RunStatus, Signal
from app.services import ai
from app.services.analysis import analyse_sites
from app.services.evaluation import detector_flags
from app.services.processing import queue_due_satellite
from tests.analysis_helpers import add_observations, history, latest
from tests.conftest import square
from tests.test_sprint3_ai import fake_answer


def make_site(client):
    r = client.post(
        "/api/sites",
        json={
            "name": "Private contact person@example.com 0551234567",
            "site_type": "park",
            "planting_category": "turf",
            "geometry": square(46.705, 24.705, 0.003),
        },
    )
    assert r.status_code == 201
    return r.json()


def test_ai_validates_nested_structure_and_the_cited_figure():
    facts = [{"id": "F1", "label": "NDVI", "value": 0.1834}, {"id": "F2", "label": "Area", "value": 5000}]
    good = fake_answer("signal_brief", facts)
    assert ai.validate("signal_brief", good, facts) == []
    for bad in (
        None,
        [],
        {"headline": "test"},
        {**good, "summary": None},
        {**good, "explanations": ["bad"]},
        {**good, "extra": "not in schema"},
    ):
        assert ai.validate("signal_brief", bad, facts)
    for text in ("NDVI is -0.1834.", "NDVI is 0.18.", "NDVI is 5000.", "NDVI is 18.34%."):
        changed = {**good, "summary": {"text": text, "fact_ids": ["F1"]}}
        assert ai.validate("signal_brief", changed, facts), text


def test_private_site_name_excluded_and_review_does_not_change_detector(as_role, db):
    manager = as_role(Role.manager)
    site = make_site(manager)
    sid = uuid.UUID(site["id"])
    add_observations(
        db,
        sid,
        history(0.35, 0.03, 0.01, [2025]) + latest([("2026-05-05", 0.2), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]),
    )
    analyse_sites(db)
    signal = db.query(Signal).filter_by(site_id=sid).one()
    assert str(sid) in detector_flags(db)
    manager.post(f"/api/signals/{signal.id}/dismiss", json={"reason": "Review decision"})
    assert str(sid) in detector_flags(db)
    import json

    assert "person@example.com" not in json.dumps(ai.signal_facts(db, signal))
    assert "0551234567" not in json.dumps(ai.signal_facts(db, signal))


def test_scheduler_persists_timing_and_does_not_spin_on_failure(as_role, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "satellite_auto_refresh", True)
    assert queue_due_satellite(db) == []
    make_site(as_role(Role.manager))
    now = datetime.now(UTC)
    runs = queue_due_satellite(db, now)
    assert {r.kind.value for r in runs} == {"sentinel2", "landsat_lst"}
    assert queue_due_satellite(db, now) == []
    for run in runs:
        run.status = RunStatus.failed
    db.commit()
    assert queue_due_satellite(db, now + timedelta(hours=1)) == []
    assert len(queue_due_satellite(db, now + timedelta(hours=25))) == 2


def test_resolved_dates_and_activity_actor_validation(as_role):
    manager = as_role(Role.manager)
    site = make_site(manager)
    assert manager.get(f"/api/sites/{site['id']}/water", params={"start": "2100-01-01"}).status_code == 422
    assert manager.get("/api/overview", params={"start": "2100-01-01"}).status_code == 422
    for kind in ("signals", "tasks"):
        assert (
            manager.get(f"/api/exports/{kind}.csv", params={"start": "2026-06-02", "end": "2026-06-01"}).status_code
            == 422
        )
    assert as_role(Role.admin).get("/api/activity", params={"user_id": "invalid"}).status_code == 422


def test_failed_after_chip_does_not_relabel_the_previous_image(as_role, db, monkeypatch):
    from app.services.imagery import generate_signal_images

    site = make_site(as_role(Role.manager))
    sid = uuid.UUID(site["id"])
    add_observations(
        db,
        sid,
        history(0.35, 0.03, 0.01, [2025]) + latest([("2026-05-05", 0.2), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]),
    )
    analyse_sites(db)
    signal = db.query(Signal).filter_by(site_id=sid).one()
    signal.after_image = "previous.png"
    signal.evidence = signal.evidence | {"after_image_obs": str(uuid.uuid4())}
    db.commit()
    monkeypatch.setattr("app.services.imagery.chip_for_observation", lambda *args: None)
    generate_signal_images(db, None, [signal.id])
    assert signal.after_image is None


def test_boundary_change_retains_old_evidence_and_reprocesses_the_same_scene(as_role, db, tmp_path):
    from datetime import date

    from app.models import LstObservation, Observation, Site, WeatherDaily
    from app.services.processing import claim_next_run, execute_run
    from tests.satellite_fakes import FakeSource, write_scene

    manager = as_role(Role.manager)
    site = make_site(manager)
    sid = uuid.UUID(site["id"])
    scene = write_scene(tmp_path, "S2_BOUNDARY_REVISION")

    def run():
        queued = manager.post("/api/processing-runs", json={"start_date": "2025-06-01", "end_date": "2025-06-30"})
        assert queued.status_code == 202
        result = execute_run(db, claim_next_run(db), FakeSource([scene]))
        assert result.status == RunStatus.succeeded
        return result

    assert run().items_written == 1
    original_id = db.query(Observation).one().id
    db.add(WeatherDaily(site_id=sid, day=date(2025, 6, 1), et0_mm=5, source="constructed"))
    db.add(
        LstObservation(
            site_id=sid,
            scene_id="CONSTRUCTED",
            platform="landsat-9",
            acquired_on=date(2025, 6, 1),
            site_c=35,
            surround_c=40,
            site_pixels=20,
            surround_pixels=50,
            valid_share=1,
            usable=True,
        )
    )
    db.commit()
    payload = {k: site.get(k) for k in ("name", "name_ar", "site_type", "planting_category", "notes")}
    payload["geometry"] = square(46.706, 24.705, 0.002)
    updated = manager.put(f"/api/sites/{sid}", json=payload)
    assert updated.status_code == 200, updated.text
    assert manager.get(f"/api/sites/{sid}/observations").json()["observations"] == []
    assert manager.get(f"/api/sites/{sid}/heat").json()["latest"] is None
    assert manager.get(f"/api/sites/{sid}/water").json()["period"]["days_with_data"] == 0
    db.expire_all()
    assert db.get(Site, sid).boundary_version == 2
    assert db.get(Site, sid).boundary_history[0]["version"] == 1
    assert db.get(Observation, original_id).boundary_version == 1
    assert run().items_written == 1  # same acquisition, new spatial boundary
    assert db.query(Observation).count() == 2  # old record preserved, never overwritten
    current = manager.get(f"/api/sites/{sid}/observations").json()["observations"]
    assert len(current) == 1
