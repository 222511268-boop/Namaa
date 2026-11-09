"""Builders for constructed NDVI histories used by analysis tests (not real data)."""

import math
import uuid
from datetime import UTC, date, datetime, timedelta

from app.models import Observation
from app.services.analysis import Obs

NOISE = (1, -1, 0.5, -0.5, 0, 0.8, -0.8)


def history(level: float, amplitude: float, noise: float, years: list[int], every_days: int = 5) -> list[Obs]:
    out = []
    for year in years:
        d, i = date(year, 1, 1), 0
        while d.year == year:
            doy = d.timetuple().tm_yday
            v = level + amplitude * math.sin(2 * math.pi * (doy - 80) / 365) + noise * NOISE[i % len(NOISE)]
            out.append(Obs(uuid.uuid4(), d, round(v, 4), f"CONSTRUCTED_{d.isoformat()}"))
            d += timedelta(days=every_days)
            i += 1
    return out


def case_series(case: dict) -> list[Obs]:
    h = case["history"]
    obs = history(h["level"], h["amplitude"], h["noise"], h["years"], h.get("every_days", 5))
    for day, v in case["latest"]:
        obs.append(Obs(uuid.uuid4(), date.fromisoformat(day), v, f"CONSTRUCTED_{day}"))
    return obs


def add_observations(db, site_id, series: list[Obs]) -> None:
    """Store constructed observations for a site (usable, full valid share)."""
    for o in series:
        db.add(
            Observation(
                id=o.id,
                site_id=site_id,
                scene_id=o.scene_id,
                platform="CONSTRUCTED",
                acquired_at=datetime(o.day.year, o.day.month, o.day.day, 7, 30, tzinfo=UTC),
                acquired_on=o.day,
                processing_baseline="05.11",
                ndvi_mean=o.ndvi,
                ndvi_std=0.02,
                ndmi_mean=0.05,
                ndmi_std=0.01,
                valid_pixels=100,
                total_pixels=100,
                valid_share=1.0,
                usable=True,
            )
        )
    db.commit()


def latest(points: list[tuple[str, float]]) -> list[Obs]:
    """Constructed recent observations from (ISO date, NDVI) pairs."""
    return [Obs(uuid.uuid4(), date.fromisoformat(d), v, f"CONSTRUCTED_{d}") for d, v in points]
