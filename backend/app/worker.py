"""Background worker: claims queued processing runs (Sentinel-2, Landsat surface temperature, weather) and
executes them. It also queues a weather update once a day.

Run with:  python -m app.worker
"""

import logging
import signal
import time
from datetime import UTC, datetime

from app.config import get_settings
from app.db import SessionLocal
from app.models import RunKind, RunStatus
from app.services.heat import LandsatSource, execute_lst_run
from app.services.processing import (
    analyse_after_run,
    claim_next_run,
    execute_run,
    queue_due_satellite,
    requeue_interrupted_runs,
)
from app.services.satellite import PlanetaryComputerSource
from app.services.weather import execute_weather_run, queue_weather_run, weather_due

log = logging.getLogger("namaa.worker")
_stop = False


def _handle_stop(*_):
    global _stop
    _stop = True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    s = get_settings()
    sentinel = PlanetaryComputerSource(s.stac_api_url, s.stac_collection, s.scene_max_cloud_cover)
    landsat = LandsatSource(s.stac_api_url, s.landsat_collection, s.landsat_max_cloud_cover)
    log.info("Worker started; polling every %.0f s", s.worker_poll_seconds)
    with SessionLocal() as db:
        if n := requeue_interrupted_runs(db):
            log.info("Re-queued %d interrupted run(s)", n)
    while not _stop:
        with SessionLocal() as db:
            for automatic in queue_due_satellite(db):
                log.info("Queued scheduled %s update %s", automatic.kind.value, automatic.id)
            if s.weather_auto_refresh and weather_due(db):
                log.info("Queued daily weather update %s", queue_weather_run(db).id)
            run = claim_next_run(db)
            if run is not None:
                log.info("Processing %s run %s", run.kind.value, run.id)
                try:
                    if run.kind == RunKind.weather:
                        execute_weather_run(db, run)
                    elif run.kind == RunKind.landsat_lst:
                        execute_lst_run(db, run, landsat)
                    else:
                        execute_run(db, run, sentinel)
                    try:
                        analyse_after_run(db, run, sentinel)
                    except Exception:  # analysis failure must not hide a completed data run
                        log.exception("Analysis after run %s failed", run.id)
                        db.rollback()
                except Exception:  # never leave a run stuck in 'running'
                    log.exception("Run %s crashed", run.id)
                    db.rollback()
                    run.status = RunStatus.failed
                    run.finished_at = datetime.now(UTC)
                    run.error = "The run stopped unexpectedly. See the worker log for details."
                    db.commit()
                log.info("Run %s finished with status %s", run.id, run.status.value)
                continue
        time.sleep(s.worker_poll_seconds)


if __name__ == "__main__":
    main()
