"""Seasonal baselines, decline detection, and priority scoring (Sprint 2, US09-US11).

The method in brief:
- Baseline for (site, month m): usable observations from years before the target year, months m-1..m+1;
  median NDVI and robust SD (1.4826 x MAD, floor 0.02); needs at least 8 observations.
- Signal when the latest 3 usable observations all have z <= -2 and NDVI - median <= -0.05.
- Priority 0-100 = 50 severity + 20 persistence + 20 size + 10 site type.
- Heat (Sprint 3, US20): when the site has recent surface temperature data, those four factors are scaled to 90 %
  and a heat factor adds up to 10 points: 10 x the percentile of the site's surrounding-area land surface
  temperature among all sites measured on the same Landsat date. Sites without heat data keep the four-factor
  score and are marked "no heat data".
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import numpy as np
from geoalchemy2.shape import to_shape
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ACTIVE_SIGNAL_STATUSES,
    DecisionType,
    LstObservation,
    Observation,
    Signal,
    SignalDecision,
    SignalStatus,
    Site,
    SiteBaseline,
    SiteStatus,
    SiteType,
    current_boundary,
)

# ---------------------------------------------------------------- pure calculations


@dataclass(frozen=True)
class Obs:
    id: object
    day: date
    ndvi: float
    scene_id: str = ""


@dataclass(frozen=True)
class Baseline:
    month: int
    target_year: int
    n_obs: int
    median: float | None
    robust_sd: float | None
    p10: float | None
    p90: float | None
    years: tuple[int, ...]
    available: bool


def _window(month: int) -> set[int]:
    return {(month - 2) % 12 + 1, month, month % 12 + 1}


def compute_baselines(observations: list[Obs], target_year: int, min_obs: int, min_sd: float) -> dict[int, Baseline]:
    """Baseline for each month of the target year from observations in earlier years."""
    earlier = [o for o in observations if o.day.year < target_year]
    out: dict[int, Baseline] = {}
    for month in range(1, 13):
        months = _window(month)
        vals = [o for o in earlier if o.day.month in months]
        years = tuple(sorted({o.day.year for o in vals}))
        if len(vals) < min_obs:
            out[month] = Baseline(month, target_year, len(vals), None, None, None, None, years, False)
            continue
        arr = np.array([o.ndvi for o in vals], dtype=float)
        median = float(np.median(arr))
        mad = float(np.median(np.abs(arr - median)))
        sd = max(1.4826 * mad, min_sd)
        out[month] = Baseline(
            month,
            target_year,
            len(vals),
            median,
            sd,
            float(np.percentile(arr, 10)),
            float(np.percentile(arr, 90)),
            years,
            True,
        )
    return out


@dataclass
class Evaluated:
    obs: Obs
    baseline: Baseline | None
    z: float | None = None
    deviation: float | None = None

    @property
    def below(self) -> bool:
        return self.z is not None


def evaluate(obs: Obs, baseline: Baseline | None) -> Evaluated:
    if baseline is None or not baseline.available:
        return Evaluated(obs, baseline)
    dev = obs.ndvi - baseline.median
    return Evaluated(obs, baseline, z=dev / baseline.robust_sd, deviation=dev)


@dataclass
class Detection:
    triggered: bool
    reason: str
    window: list[Evaluated] = field(default_factory=list)
    run_start: date | None = None  # first observation of the unbroken below-range run that ends now
    run_length: int = 0

    @property
    def latest(self) -> Evaluated:
        return self.window[-1]

    @property
    def mean_z(self) -> float:
        return float(np.mean([e.z for e in self.window]))


def detect(
    observations: list[Obs], baselines: dict[int, Baseline], k: int, z_threshold: float, min_drop: float
) -> Detection:
    """Apply the documented rule to the latest k usable observations (sorted by date)."""
    obs = sorted(observations, key=lambda o: o.day)
    if len(obs) < k:
        return Detection(False, f"Fewer than {k} usable observations")
    window = [evaluate(o, baselines.get(o.day.month)) for o in obs[-k:]]
    if any(e.z is None for e in window):
        return Detection(False, "Baseline not available for the latest observations", window)

    def below(e: Evaluated) -> bool:
        return e.z is not None and e.z <= z_threshold and e.deviation <= -min_drop

    if not all(below(e) for e in window):
        return Detection(False, "Within or near the seasonal range", window)
    # Persistence: walk back over consecutive earlier observations that also meet the rule.
    run_start, run_length = window[0].obs.day, k
    for o in reversed(obs[:-k]):
        # Observations from the baseline years are part of the baseline itself, so the run stops there.
        if o.day.year < obs[-1].day.year or not below(evaluate(o, baselines.get(o.day.month))):
            break
        run_start, run_length = o.day, run_length + 1
    return Detection(
        True, "Latest observations are consistently below the seasonal range", window, run_start, run_length
    )


SITE_TYPE_WEIGHT = {
    SiteType.park: 1.0,
    SiteType.garden: 1.0,
    SiteType.plaza: 0.7,
    SiteType.median: 0.5,
    SiteType.other: 0.5,
}


@dataclass(frozen=True)
class Heat:
    """A site's surrounding-area surface temperature and its percentile among sites measured on the same date."""

    surround_c: float
    acquired_on: date
    percentile: float  # 0..1
    sites_compared: int


HEAT_WEIGHT = 10.0
MIN_SITES_FOR_HEAT_RANK = 3


def priority(
    mean_z: float, first: date, last: date, area_m2: float, site_type: SiteType, heat: Heat | None = None
) -> tuple[float, dict]:
    """Priority score 0-100 and each factor's contribution in points."""
    severity = min(abs(mean_z) / 4.0, 1.0)
    persistence = min((last - first).days / 30.0, 1.0)
    size = min(max(math.log10(max(area_m2, 1) / 5000.0) / math.log10(50.0), 0.0), 1.0)
    type_w = SITE_TYPE_WEIGHT[site_type]
    scale = (100 - HEAT_WEIGHT) / 100 if heat is not None else 1.0
    factors = {
        "severity": round(50 * scale * severity, 1),
        "persistence": round(20 * scale * persistence, 1),
        "size": round(20 * scale * size, 1),
        "site_type": round(10 * scale * type_w, 1),
    }
    if heat is not None:
        factors["heat"] = round(HEAT_WEIGHT * heat.percentile, 1)
    score = round(sum(factors.values()), 1)
    if heat is not None:
        factors["heat_c"] = round(heat.surround_c, 1)
        factors["heat_date"] = heat.acquired_on.isoformat()
        factors["heat_percentile"] = round(100 * heat.percentile)
        factors["heat_sites_compared"] = heat.sites_compared
    else:
        factors["heat"] = None  # no heat data: scored on the four factors only
    return score, factors


def percentile_rank(value: float, values: list[float]) -> float:
    """Share of values below `value`, counting ties as half (0..1)."""
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    return (below + 0.5 * equal) / len(values)


def heat_context(db: Session, today: date | None = None) -> dict:
    """Heat information per site, from each site's latest usable surface temperature within the allowed age."""
    s = get_settings()
    cutoff = (today or date.today()) - timedelta(days=s.heat_max_age_days)
    usable = (
        Site.status == SiteStatus.active,
        LstObservation.usable.is_(True),
        current_boundary(LstObservation),
        LstObservation.surround_c.is_not(None),
    )
    latest = dict(
        db.execute(
            select(LstObservation.site_id, func.max(LstObservation.acquired_on))
            .join(Site, Site.id == LstObservation.site_id)
            .where(*usable, LstObservation.acquired_on >= cutoff)
            .group_by(LstObservation.site_id)
        ).all()
    )
    if not latest:
        return {}
    rows = db.execute(
        select(LstObservation.site_id, LstObservation.acquired_on, LstObservation.surround_c)
        .join(Site, Site.id == LstObservation.site_id)
        .where(*usable, LstObservation.acquired_on.in_(set(latest.values())))
    ).all()
    by_day: dict[date, list[float]] = {}
    for _, day, v in rows:
        by_day.setdefault(day, []).append(v)
    out = {}
    for site_id, day, v in rows:
        if latest.get(site_id) != day or len(by_day[day]) < MIN_SITES_FOR_HEAT_RANK:
            continue
        out[site_id] = Heat(v, day, percentile_rank(v, by_day[day]), len(by_day[day]))
    return out


# ---------------------------------------------------------------- database orchestration


@dataclass
class AnalysisSummary:
    sites_evaluated: int = 0
    baselines_written: int = 0
    signals_created: int = 0
    signals_updated: int = 0
    signals_reopened: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    changed_signal_ids: list = field(default_factory=list)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _usable_obs(db: Session, site_id) -> list[Obs]:
    rows = db.execute(
        select(Observation.id, Observation.acquired_on, Observation.ndvi_mean, Observation.scene_id)
        .where(
            Observation.site_id == site_id,
            current_boundary(Observation),
            Observation.usable.is_(True),
            Observation.ndvi_mean.is_not(None),
        )
        .order_by(Observation.acquired_on)
    ).all()
    return [Obs(r[0], r[1], r[2], r[3]) for r in rows]


def refresh_baselines(db: Session, site: Site, obs: list[Obs]) -> dict[int, Baseline]:
    s = get_settings()
    if not obs:
        db.execute(delete(SiteBaseline).where(SiteBaseline.site_id == site.id))
        return {}
    target_year = obs[-1].day.year
    baselines = compute_baselines(obs, target_year, s.baseline_min_obs, s.baseline_min_sd)
    db.execute(delete(SiteBaseline).where(SiteBaseline.site_id == site.id))
    now = datetime.now(UTC)
    for b in baselines.values():
        db.add(
            SiteBaseline(
                site_id=site.id,
                month=b.month,
                target_year=b.target_year,
                n_obs=b.n_obs,
                median_ndvi=b.median,
                robust_sd=b.robust_sd,
                p10=b.p10,
                p90=b.p90,
                years=",".join(str(y) for y in b.years),
                available=b.available,
                computed_at=now,
            )
        )
    return baselines


def _evidence(det: Detection) -> dict:
    return {
        "rule": {
            "window": len(det.window),
            "z_threshold": get_settings().detection_z,
            "min_drop": get_settings().detection_min_drop,
        },
        "observations": [
            {
                "observation_id": str(e.obs.id),
                "date": e.obs.day.isoformat(),
                "scene_id": e.obs.scene_id,
                "ndvi": round(e.obs.ndvi, 4),
                "baseline_median": round(e.baseline.median, 4),
                "baseline_sd": round(e.baseline.robust_sd, 4),
                "deviation": round(e.deviation, 4),
                "z": round(e.z, 2),
            }
            for e in det.window
        ],
    }


def _apply_detection(signal: Signal, site: Site, det: Detection, heat: Heat | None = None) -> None:
    if (signal.evidence or {}).get("boundary_version", 1) != site.boundary_version:
        signal.before_image = signal.after_image = None
        signal.before_obs_id = None
        signal.evidence = {}
    latest = det.latest
    first_day, last_day = det.run_start or det.window[0].obs.day, latest.obs.day
    score, factors = priority(det.mean_z, first_day, last_day, site.area_m2, site.site_type, heat)
    signal.first_obs_on = first_day
    signal.last_obs_on = last_day
    signal.latest_ndvi = latest.obs.ndvi
    signal.baseline_median = latest.baseline.median
    signal.baseline_sd = latest.baseline.robust_sd
    signal.deviation = latest.deviation
    signal.z_score = latest.z
    signal.priority_score = score
    signal.priority_factors = factors | {"mean_z": round(det.mean_z, 2), "run_length": det.run_length}
    # Keep the record of which observation the current 'after' image shows, so it is not regenerated needlessly.
    kept = {k: v for k, v in (signal.evidence or {}).items() if k == "after_image_obs"}
    signal.evidence = (
        _evidence(det)
        | kept
        | {
            "boundary_version": site.boundary_version,
            "boundary_geometry": to_shape(site.geom).__geo_interface__,
            "site_area_m2": site.area_m2,
        }
    )
    signal.after_obs_id = latest.obs.id


def _before_observation(obs: list[Obs], target: date) -> Obs | None:
    """Usable observation from an earlier year closest to the same day of year."""
    earlier = [o for o in obs if o.day.year < target.year]
    if not earlier:
        return None

    def distance(o: Obs) -> int:
        d = abs(o.day.timetuple().tm_yday - target.timetuple().tm_yday)
        return min(d, 365 - d) + 400 * (target.year - o.day.year - 1)  # prefer the most recent earlier year

    return min(earlier, key=distance)


def analyse_site(db: Session, site: Site, summary: AnalysisSummary, heat: dict | None = None) -> None:
    s = get_settings()
    site_heat = (heat or {}).get(site.id)
    obs = _usable_obs(db, site.id)
    baselines = refresh_baselines(db, site, obs)
    summary.baselines_written += len(baselines)
    if site.low_confidence:
        summary.skip("low confidence site")
        return
    summary.sites_evaluated += 1
    det = detect(obs, baselines, s.detection_window, s.detection_z, s.detection_min_drop)
    if not det.triggered:
        summary.skip(det.reason)
        return

    earliest_new = det.window[0].obs.day  # reopening depends on the triggering window, not the whole run
    # populate_existing: always read the current state; decisions are made in other sessions (API requests).
    fresh = {"populate_existing": True}
    active = db.scalar(
        select(Signal)
        .where(Signal.site_id == site.id, Signal.status.in_(ACTIVE_SIGNAL_STATUSES))
        .execution_options(**fresh)
    )
    if active is not None:
        _apply_detection(active, site, det, site_heat)
        if active.before_obs_id is None:
            before = _before_observation(obs, det.latest.obs.day)
            active.before_obs_id = before.id if before else None
        summary.signals_updated += 1
        summary.changed_signal_ids.append(active.id)
        return

    last = db.scalar(
        select(Signal).where(Signal.site_id == site.id).order_by(Signal.detected_at.desc()).execution_options(**fresh)
    )
    if (
        last is not None
        and (last.evidence or {}).get("boundary_version", 1) == site.boundary_version
        and earliest_new <= last.last_obs_on
    ):
        # The same observations already led to a dismissed or closed signal; only new evidence counts.
        summary.skip("already reviewed")
        return
    if last is not None and last.status == SignalStatus.dismissed:
        last.status = SignalStatus.open
        last.reopened_count += 1
        _apply_detection(last, site, det, site_heat)
        if last.before_obs_id is None:
            before = _before_observation(obs, det.latest.obs.day)
            last.before_obs_id = before.id if before else None
        db.add(
            SignalDecision(
                signal_id=last.id,
                decision=DecisionType.reopened,
                reason="New observations met the detection rule again.",
            )
        )
        summary.signals_reopened += 1
        summary.changed_signal_ids.append(last.id)
        return

    signal = Signal(site_id=site.id, status=SignalStatus.open, reopened_count=0)
    _apply_detection(signal, site, det, site_heat)
    before = _before_observation(obs, det.latest.obs.day)
    signal.before_obs_id = before.id if before else None
    db.add(signal)
    db.flush()
    summary.signals_created += 1
    summary.changed_signal_ids.append(signal.id)


def analyse_sites(db: Session, site_ids: list | None = None) -> AnalysisSummary:
    """Recalculate baselines and run detection for active sites (all, or the given ones)."""
    summary = AnalysisSummary()
    heat = heat_context(db)
    q = select(Site).where(Site.status == SiteStatus.active)
    if site_ids:
        q = q.where(Site.id.in_(site_ids))
    for site in db.scalars(q):
        analyse_site(db, site, summary, heat)
    db.commit()
    return summary


def rescore_active_signals(db: Session) -> int:
    """Recalculate priority for open and under-inspection signals, e.g. after new surface temperature data."""
    heat = heat_context(db)
    n = 0
    for sig in db.scalars(select(Signal).where(Signal.status.in_(ACTIVE_SIGNAL_STATUSES))):
        f = sig.priority_factors or {}
        if "mean_z" not in f:
            continue
        site = sig.site
        if (sig.evidence or {}).get("boundary_version", 1) != site.boundary_version:
            continue
        score, factors = priority(
            f["mean_z"], sig.first_obs_on, sig.last_obs_on, site.area_m2, site.site_type, heat.get(site.id)
        )
        sig.priority_score = score
        sig.priority_factors = factors | {"mean_z": f["mean_z"], "run_length": f.get("run_length")}
        n += 1
    db.commit()
    return n
