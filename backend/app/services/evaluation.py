"""Detection evaluation against team-labelled reference sites (charter KPI "Detection evaluation").

Workflow:
1. `python -m app.cli labelling-template out.csv` writes one row per evaluated site (active, not low-confidence),
   with the detector's current result hidden in a separate column the labeller should not look at first.
2. The team labels each site by visual interpretation of Sentinel-2 imagery (and field knowledge):
   label = decline | no_decline | unsure.
3. `python -m app.cli evaluate-detection labels.csv` reports precision, recall and the confusion counts.
   'unsure' rows are excluded and counted separately.
"""

import csv
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Site, SiteStatus

TEMPLATE_FIELDS = ["site_id", "site_name", "district", "area_m2", "label", "labelled_by", "notes", "detector_result"]


def detector_flags(db: Session) -> set[str]:
    """Compute raw detector outputs independently of managers' review decisions."""
    from app.config import get_settings
    from app.services.analysis import _usable_obs, compute_baselines, detect

    settings = get_settings()
    flagged = set()
    for site in db.scalars(select(Site).where(Site.status == SiteStatus.active, Site.low_confidence.is_(False))):
        observations = _usable_obs(db, site.id)
        if not observations:
            continue
        baselines = compute_baselines(
            observations, observations[-1].day.year, settings.baseline_min_obs, settings.baseline_min_sd
        )
        if detect(
            observations, baselines, settings.detection_window, settings.detection_z, settings.detection_min_drop
        ).triggered:
            flagged.add(str(site.id))
    return flagged


def write_template(db: Session, path: str) -> int:
    flags = detector_flags(db)
    sites = db.scalars(
        select(Site).where(Site.status == SiteStatus.active, Site.low_confidence.is_(False)).order_by(Site.name)
    )
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TEMPLATE_FIELDS)
        w.writeheader()
        for s in sites:
            d = s.district
            w.writerow(
                {
                    "site_id": s.id,
                    "site_name": s.name,
                    "district": (d.name_en or d.name_ar) if d else "",
                    "area_m2": round(s.area_m2),
                    "label": "",
                    "labelled_by": "",
                    "notes": "",
                    "detector_result": "flagged" if str(s.id) in flags else "not_flagged",
                }
            )
            n += 1
    return n


@dataclass
class EvaluationResult:
    tp: int
    fp: int
    fn: int
    tn: int
    unsure: int
    unknown_sites: int

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


def evaluate(labels: dict[str, str], flagged: set[str], known_sites: set[str]) -> EvaluationResult:
    tp = fp = fn = tn = unsure = unknown = 0
    for site_id, label in labels.items():
        if site_id not in known_sites:
            unknown += 1
            continue
        label = label.strip().lower()
        if label not in ("decline", "no_decline"):
            unsure += 1
            continue
        predicted = site_id in flagged
        actual = label == "decline"
        tp += predicted and actual
        fp += predicted and not actual
        fn += (not predicted) and actual
        tn += (not predicted) and not actual
    return EvaluationResult(tp, fp, fn, tn, unsure, unknown)


def evaluate_file(db: Session, path: str) -> EvaluationResult:
    with open(path, newline="", encoding="utf-8") as fh:
        labels = {row["site_id"]: row.get("label", "") for row in csv.DictReader(fh)}
    known = {str(i) for i in db.scalars(select(Site.id))}
    return evaluate(labels, detector_flags(db), known)
