"""Daily weather for each site's location from Open-Meteo (US17).

Reference evapotranspiration (FAO-56 Penman-Monteith, `et0_fao_evapotranspiration`), maximum and minimum air
temperature and precipitation are stored per site and day. Only complete days (before today, Riyadh time) are
stored. Values come from the historical weather API; recent days it does not yet cover come from the forecast API.

Weather data by Open-Meteo.com, licensed under CC BY 4.0.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.localtime import local_today
from app.models import ProcessingRun, RunKind, RunStatus, Site, SiteStatus, WeatherDaily

log = logging.getLogger("namaa.weather")

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
DAILY_VARS = "et0_fao_evapotranspiration,temperature_2m_max,temperature_2m_min,precipitation_sum"
RIYADH = ZoneInfo("Asia/Riyadh")
BATCH = 50  # coordinates per request
RECENT_DAYS = 14  # days the archive may not yet cover; filled from the forecast API


class WeatherError(RuntimeError):
    pass


@dataclass(frozen=True)
class DailyWeather:
    day: date
    et0_mm: float | None
    tmax_c: float | None
    tmin_c: float | None
    precip_mm: float | None


def riyadh_today() -> date:
    return local_today()


def parse_daily(payload: dict) -> list[DailyWeather]:
    d = payload.get("daily") or {}
    days = d.get("time") or []
    col = lambda k: d.get(k) or [None] * len(days)  # noqa: E731
    return [
        DailyWeather(date.fromisoformat(t), e, hi, lo, p)
        for t, e, hi, lo, p in zip(
            days,
            col("et0_fao_evapotranspiration"),
            col("temperature_2m_max"),
            col("temperature_2m_min"),
            col("precipitation_sum"),
            strict=True,
        )
    ]


def _get(client: httpx.Client, url: str, chunk, a: date, b: date) -> list[dict]:
    params = {
        "latitude": ",".join(f"{lat:.4f}" for _, lat in chunk),
        "longitude": ",".join(f"{lon:.4f}" for lon, _ in chunk),
        "daily": DAILY_VARS,
        "timezone": "Asia/Riyadh",
        "start_date": a.isoformat(),
        "end_date": b.isoformat(),
    }
    try:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WeatherError(f"The weather service could not be reached: {exc}") from exc
    results = data if isinstance(data, list) else [data]
    if len(results) != len(chunk):
        raise WeatherError("The weather service returned an unexpected number of locations.")
    return results


def fetch(points: list[tuple[float, float]], start: date, end: date) -> list[list[tuple[DailyWeather, str]]]:
    """Daily weather for each (lon, lat) point and day in [start, end], with the API each value came from.

    The historical archive is used first; days it does not yet cover within the last two weeks are filled from
    the forecast API, which keeps recent past days.
    """
    s = get_settings()
    recent_start = max(start, riyadh_today() - timedelta(days=RECENT_DAYS))
    out: list[list[tuple[DailyWeather, str]]] = [[] for _ in points]
    headers = {"User-Agent": s.http_user_agent}
    with httpx.Client(timeout=s.weather_timeout_s, headers=headers) as client:
        for i in range(0, len(points), BATCH):
            chunk = points[i : i + BATCH]
            archive = _get(client, s.weather_archive_url, chunk, start, end)
            recent = _get(client, s.weather_forecast_url, chunk, recent_start, end) if recent_start <= end else None
            for j, res in enumerate(archive):
                days = {d.day: (d, "open-meteo-archive") for d in parse_daily(res) if d.et0_mm is not None}
                if recent is not None:
                    for d in parse_daily(recent[j]):
                        if d.day not in days and d.et0_mm is not None:
                            days[d.day] = (d, "open-meteo-forecast")
                out[i + j] = [days[k] for k in sorted(days)]
    return out


def queue_weather_run(db: Session, user_id=None, days: int | None = None) -> ProcessingRun:
    days = days or get_settings().weather_history_days
    end = riyadh_today() - timedelta(days=1)
    run = ProcessingRun(
        kind=RunKind.weather,
        status=RunStatus.queued,
        params={"start_date": (end - timedelta(days=days - 1)).isoformat(), "end_date": end.isoformat()},
        requested_by=user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def weather_due(db: Session) -> bool:
    """True when no weather run is pending and the newest stored weather is older than the refresh interval."""
    pending = db.scalar(
        select(func.count())
        .select_from(ProcessingRun)
        .where(ProcessingRun.kind == RunKind.weather, ProcessingRun.status.in_((RunStatus.queued, RunStatus.running)))
    )
    if pending:
        return False
    if not db.scalar(select(func.count()).select_from(Site).where(Site.status == SiteStatus.active)):
        return False
    last = db.scalar(
        select(func.max(ProcessingRun.created_at)).where(
            ProcessingRun.kind == RunKind.weather, ProcessingRun.status != RunStatus.failed
        )
    )
    last_failed = db.scalar(
        select(func.max(ProcessingRun.created_at)).where(
            ProcessingRun.kind == RunKind.weather, ProcessingRun.status == RunStatus.failed
        )
    )
    now = datetime.now(UTC)
    interval = timedelta(hours=get_settings().weather_refresh_hours)
    # After a failure, wait an hour before trying again rather than retrying every poll.
    if last_failed and (last is None or last_failed > last) and now - last_failed < timedelta(hours=1):
        return False
    return last is None or now - last >= interval


def execute_weather_run(db: Session, run: ProcessingRun) -> ProcessingRun:
    from app.services.processing import _finish, _note

    params = run.params or {}
    start, end = date.fromisoformat(params["start_date"]), date.fromisoformat(params["end_date"])
    run.scenes_found = run.scenes_processed = run.items_written = run.items_skipped = 0
    q = select(Site).where(Site.status == SiteStatus.active)
    if params.get("site_ids"):
        q = q.where(Site.id.in_(params["site_ids"]))
    sites = list(db.scalars(q))
    if not sites:
        return _finish(db, run, RunStatus.failed, "No active sites to fetch weather for.")
    points = []
    for site in sites:
        c = to_shape(site.geom).representative_point()
        points.append((c.x, c.y))
    try:
        series = fetch(points, start, end)
    except WeatherError as exc:
        _note(run, "Stored weather values were kept; estimates use the last stored values.")
        return _finish(db, run, RunStatus.failed, str(exc))
    expected = (end - start).days + 1
    for site, days in zip(sites, series, strict=True):
        rows = [
            {
                "site_id": site.id,
                "boundary_version": site.boundary_version,
                "day": d.day,
                "et0_mm": d.et0_mm,
                "tmax_c": d.tmax_c,
                "tmin_c": d.tmin_c,
                "precip_mm": d.precip_mm,
                "source": src,
                "fetched_at": datetime.now(UTC),
            }
            for d, src in days
        ]
        run.items_skipped += expected - len(rows)  # days without a value from either API
        if rows:
            stmt = insert(WeatherDaily).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_weather_site_day",
                set_={k: stmt.excluded[k] for k in ("et0_mm", "tmax_c", "tmin_c", "precip_mm", "source", "fetched_at")},
            )
            db.execute(stmt)
        run.items_written += len(rows)
        run.scenes_processed += 1  # here: locations processed
    run.scenes_found = len(sites)
    _note(run, f"Weather for {len(sites)} sites from {start.isoformat()} to {end.isoformat()}. {ATTRIBUTION}.")
    return _finish(db, run, RunStatus.succeeded, None)
