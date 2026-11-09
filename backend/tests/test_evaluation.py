"""Detection evaluation tooling (charter KPI): confusion counts, precision and recall."""

import csv
import uuid

import pytest

from app.models import Role
from app.services.analysis import analyse_sites
from app.services.evaluation import evaluate, evaluate_file, write_template
from tests.analysis_helpers import add_observations, history, latest
from tests.conftest import square


def test_counts_precision_recall():
    a, b, c, d, e = (str(uuid.uuid4()) for _ in range(5))
    labels = {a: "decline", b: "no_decline", c: "decline", d: "no_decline", e: "unsure", "x": "decline"}
    r = evaluate(labels, flagged={a, b}, known_sites={a, b, c, d, e})
    assert (r.tp, r.fp, r.fn, r.tn, r.unsure, r.unknown_sites) == (1, 1, 1, 1, 1, 1)
    assert r.precision == 0.5 and r.recall == 0.5


def test_no_positives_gives_none():
    r = evaluate({"a": "no_decline"}, flagged=set(), known_sites={"a"})
    assert r.precision is None and r.recall is None


def test_template_round_trip(as_role, db, tmp_path):
    m = as_role(Role.manager)
    declining = m.post(
        "/api/sites",
        json={
            "name": "Declining",
            "site_type": "park",
            "planting_category": "turf",
            "geometry": square(46.705, 24.705, 0.003),
        },
    ).json()
    stable = m.post(
        "/api/sites",
        json={
            "name": "Stable",
            "site_type": "park",
            "planting_category": "turf",
            "geometry": square(46.712, 24.705, 0.003),
        },
    ).json()
    add_observations(
        db,
        uuid.UUID(declining["id"]),
        history(0.35, 0.03, 0.01, [2025]) + latest([("2026-05-05", 0.2), ("2026-05-10", 0.19), ("2026-05-15", 0.18)]),
    )
    add_observations(db, uuid.UUID(stable["id"]), history(0.35, 0.03, 0.01, [2025]))
    analyse_sites(db)
    path = tmp_path / "labels.csv"
    assert write_template(db, str(path)) == 2
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert {r["site_name"]: r["detector_result"] for r in rows} == {"Declining": "flagged", "Stable": "not_flagged"}
    for r in rows:
        r["label"] = "decline" if r["site_name"] == "Declining" else "no_decline"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    result = evaluate_file(db, str(path))
    assert result.precision == pytest.approx(1.0) and result.recall == pytest.approx(1.0)
