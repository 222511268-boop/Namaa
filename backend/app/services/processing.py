"""Processing runs: queueing, claiming by the worker, and execution.

Run kinds executed by the worker: Sentinel-2 vegetation indices (sentinel2), Landsat surface temperature
(landsat_lst) and weather for water-demand estimates (weather). OpenStreetMap imports run inside the request.
"""

import logging
from datetime import UTC, datetime, timedelta

from geoalchemy2.shape import to_shape
from shapely.ops import unary_union
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Observation, ProcessingRun, RunKind, RunStatus, Site, SiteStatus, current_boundary
from app.services.satellite import SceneReader, SceneSource, SceneSourceError

log = logging.getLogger("namaa.processing")
MAX_MESSAGES = 200


WORKER_KINDS = (RunKind.sentinel2, RunKind.landsat_lst, RunKind.weather)


def queue_due_satellite(db: Session, now: datetime | None = None) -> list[ProcessingRun]:
    """Daily overlapping refresh; stored run timestamps survive restarts and failures do not spin."""
    settings = get_settings()
    if not settings.satellite_auto_refresh or not db.scalar(
        select(Site.id).where(Site.status == SiteStatus.active).limit(1)
    ):
        return []
    now = now or datetime.now(UTC)
    queued = []
    for kind in (RunKind.sentinel2, RunKind.landsat_lst):
        last = db.scalar(
            select(ProcessingRun).where(ProcessingRun.kind == kind).order_by(ProcessingRun.created_at.desc()).limit(1)
        )
        if last and (
            last.status in (RunStatus.queued, RunStatus.running)
            or last.created_at > now - timedelta(hours=settings.satellite_refresh_hours)
        ):
            continue
        end = now.date()
        queued.append(queue_run(db, end - timedelta(days=settings.satellite_refresh_days - 1), end, None, None, kind))
    return queued


def queue_run(db: Session, start, end, site_ids, user_id, kind: RunKind = RunKind.sentinel2) -> ProcessingRun:
    run = ProcessingRun(
        kind=kind,
        status=RunStatus.queued,
        params={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "site_ids": [str(s) for s in site_ids] if site_ids else None,
        },
        requested_by=user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def requeue_interrupted_runs(db: Session) -> int:
    """Return runs left 'running' by a stopped worker to the queue (safe: processing is idempotent).

    Called when the worker starts. Assumes a single worker, as deployed by docker-compose.yml.
    """
    runs = list(
        db.scalars(
            select(ProcessingRun).where(ProcessingRun.kind.in_(WORKER_KINDS), ProcessingRun.status == RunStatus.running)
        )
    )
    for run in runs:
        run.status = RunStatus.queued
        _note(run, "Run was interrupted (worker restarted) and has been queued again.")
    db.commit()
    return len(runs)


def claim_next_run(db: Session) -> ProcessingRun | None:
    """Atomically move the oldest queued worker run to 'running' (safe with several workers)."""
    run_id = db.execute(
        text(
            "SELECT id FROM processing_runs WHERE status = 'queued' "
            "AND kind IN ('sentinel2', 'landsat_lst', 'weather') "
            "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
    ).scalar()
    if run_id is None:
        db.rollback()
        return None
    run = db.get(ProcessingRun, run_id)
    run.status = RunStatus.running
    run.started_at = datetime.now(UTC)
    db.commit()
    return run


def _note(run: ProcessingRun, message: str) -> None:
    if len(run.messages) < MAX_MESSAGES:
        run.messages = [*run.messages, message]


def _upsert(db: Session, run, site, scene, stats, usable) -> bool:
    """Store one observation per site and acquisition date; keep the one with more valid pixels.

    Returns True when a row was written.
    """
    day = scene.acquired_at.date()
    obs = db.scalar(
        select(Observation).where(
            Observation.site_id == site.id,
            Observation.acquired_on == day,
            Observation.boundary_version == site.boundary_version,
        ).with_for_update()
    )
    if obs is not None and obs.valid_pixels >= stats.valid_pixels:
        return False
    if obs is None:
        obs = Observation(site_id=site.id, acquired_on=day, boundary_version=site.boundary_version)
        db.add(obs)
    obs.run_id = run.id
    obs.scene_id = scene.id
    obs.platform = scene.platform
    obs.acquired_at = scene.acquired_at
    obs.processing_baseline = scene.processing_baseline
    obs.ndvi_mean, obs.ndvi_std = stats.ndvi_mean, stats.ndvi_std
    obs.ndmi_mean, obs.ndmi_std = stats.ndmi_mean, stats.ndmi_std
    obs.valid_pixels, obs.total_pixels = stats.valid_pixels, stats.total_pixels
    obs.valid_share = round(stats.valid_share, 4)
    obs.usable = usable
    return True


def execute_run(db: Session, run: ProcessingRun, source: SceneSource) -> ProcessingRun:
    """Process every scene in the run's date range for the selected active sites.

    New observations are committed per scene. Replacements of pre-existing observations are
    deferred until every scene succeeds, so a later failure preserves the saved measurements.
    """
    s = get_settings()
    params = run.params or {}
    # Counters describe the current attempt; a re-queued run starts again from zero (stored scenes are skipped).
    run.scenes_found = run.scenes_processed = run.items_written = run.items_skipped = 0
    q = select(Site).where(Site.status == SiteStatus.active)
    if params.get("site_ids"):
        q = q.where(Site.id.in_(params["site_ids"]))
    sites = list(db.scalars(q))
    if not sites:
        return _finish(db, run, RunStatus.failed, "No active sites to process.")

    shapes = {site.id: to_shape(site.geom) for site in sites}
    bbox = unary_union(list(shapes.values())).bounds
    try:
        scenes = source.search(bbox, params["start_date"], params["end_date"])
    except SceneSourceError as exc:
        return _finish(db, run, RunStatus.failed, str(exc))

    run.scenes_found = len(scenes)
    db.commit()
    # (site, scene) pairs already stored: re-reading them cannot change the result, so they are skipped.
    done = set(
        db.execute(
            select(Observation.site_id, Observation.scene_id).where(
                Observation.site_id.in_(list(shapes)), current_boundary(Observation)
            )
        ).all()
    )
    protected = set(
        db.execute(
            select(Observation.site_id, Observation.acquired_on, Observation.boundary_version).where(
                Observation.site_id.in_(list(shapes)), current_boundary(Observation)
            )
        ).all()
    )
    boundary_versions = {site.id: site.boundary_version for site in sites}
    replacements = []
    failures = 0
    for scene in scenes:
        targets = [site for site in sites if scene.footprint.contains(shapes[site.id])]
        pending = [site for site in targets if (site.id, scene.id) not in done]
        run.items_skipped += len(targets) - len(pending)
        if not pending:
            run.scenes_processed += 1
            db.commit()
            continue
        try:
            written = skipped = 0
            scene_replacements = []
            with SceneReader(source.signed_hrefs(scene), scene) as reader:
                for site in pending:
                    stats = reader.site_stats(shapes[site.id])
                    usable = stats.usable(s.min_valid_share, s.min_valid_pixels)
                    key = (site.id, scene.acquired_at.date(), boundary_versions[site.id])
                    if key in protected:
                        scene_replacements.append((site, scene, stats, usable))
                    elif _upsert(db, run, site, scene, stats, usable):
                        written += 1
                    else:
                        skipped += 1
            run.items_written += written
            run.items_skipped += skipped
            run.scenes_processed += 1
            db.commit()
            replacements.extend(scene_replacements)
        except Exception as exc:  # unreadable asset, network failure, etc.
            db.rollback()
            failures += 1
            log.warning("Scene %s failed: %s", scene.id, exc)
            _note(run, f"Scene {scene.id} could not be processed: {exc}")
            db.commit()

    if failures:
        return _finish(
            db,
            run,
            RunStatus.failed,
            f"{failures} of {len(scenes)} scenes could not be processed. "
            "New observations from completed scenes were saved; "
            "existing measurements were preserved. "
            "start the run again to retry the remaining scenes.",
        )
    try:
        for site, scene, stats, usable in replacements:
            # Geometry may have been edited while imagery was being read.
            db.refresh(site)
            if site.boundary_version == boundary_versions[site.id] and _upsert(db, run, site, scene, stats, usable):
                run.items_written += 1
            else:
                run.items_skipped += 1
        return _finish(db, run, RunStatus.succeeded, None)
    except Exception as exc:
        db.rollback()
        log.warning("Observation replacements for run %s failed: %s", run.id, exc)
        return _finish(
            db, run, RunStatus.failed, "Saved measurements could not be updated; start the run again to retry."
        )


def _finish(db: Session, run: ProcessingRun, status: RunStatus, error: str | None) -> ProcessingRun:
    run.status = status
    run.error = error
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run


def analyse_after_run(db: Session, run: ProcessingRun, source: SceneSource) -> None:
    """Recalculate baselines, run detection and create evidence images for the run's sites (US09-US12).

    After a surface temperature run, active signals are re-scored with the new heat data (US20).
    """
    from app.services.analysis import analyse_sites, rescore_active_signals
    from app.services.imagery import generate_signal_images

    if run.kind == RunKind.landsat_lst:
        if run.items_written:
            _note(run, f"Priority re-scored with heat data for {rescore_active_signals(db)} active signals.")
            db.commit()
        return
    if run.kind != RunKind.sentinel2 or run.scenes_processed == 0:
        return
    summary = analyse_sites(db, (run.params or {}).get("site_ids"))
    images = generate_signal_images(db, source, summary.changed_signal_ids)
    _note(
        run,
        f"Analysis: {summary.sites_evaluated} sites evaluated, {summary.signals_created} new signals, "
        f"{summary.signals_updated} updated, {summary.signals_reopened} reopened, {images} evidence images.",
    )
    db.commit()
