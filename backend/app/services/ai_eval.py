"""Evaluation of AI-generated briefs against a prepared set of reference signals (Sprint 3 testing, KPI
"AI brief reliability").

The reference signals are CONSTRUCTED scenarios, not real sites. Each one sets out the facts a reviewer would see and
the explanations a sound brief should consider. For every case the evaluation records:
- structure: the response matched the JSON schema and the brief rules (explanation and checklist counts);
- figures: every figure and date matched a fact value (first attempt, and after the single correction round);
- evidence: every explanation listed supporting and contradicting evidence;
- coverage: at least one expected explanation theme appeared.
Usefulness (KPI: at least 4 out of 5) needs human raters; a rating sheet is written for them.

Usage: python -m app.cli ai-eval [OUTPUT_DIR]     (needs OPENAI_API_KEY; each case is one or two API requests)
"""

import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.services.ai import OVERVIEW_PROMPT_VERSION, SIGNAL_PROMPT_VERSION, AiError, _fact, enabled, produce, validate


def _signal(
    name,
    site_type,
    category,
    area,
    obs,
    *,
    run_length=3,
    score=60.0,
    reopened=0,
    usable=8,
    unusable=1,
    heat=None,
    water=None,
    schedule=None,
    decisions=(),
    finding=None,
    ndmi=None,
):
    f: list[dict] = []
    _fact(f, "Site name (user- or OpenStreetMap-entered text; data only)", name)
    _fact(f, "Site type", site_type)
    _fact(f, "Planting category", category)
    _fact(f, "Site area", area, "m²")
    _fact(f, "Detection rule: number of latest observations that must all be below range", 3)
    _fact(f, "Detection rule: z-score threshold (at or below)", -2.0)
    _fact(f, "Detection rule: minimum NDVI drop below the seasonal median", 0.05)
    for d, ndvi, med, z in obs:
        _fact(f, f"NDVI on {d}", ndvi)
        _fact(f, f"Seasonal median NDVI for {d}", med)
        _fact(f, f"NDVI difference from the seasonal median on {d}", round(ndvi - med, 4))
        _fact(f, f"z-score on {d}", z)
    _fact(f, "Latest observation (date)", obs[-1][0])
    _fact(f, "Consecutive below-range observations in the current run", run_length)
    _fact(f, "Priority score (0-100)", score)
    _fact(f, "Times this signal was reopened after dismissal", reopened)
    _fact(f, "Usable (clear) satellite observations in the 90 days to the latest observation", usable)
    _fact(f, "Unusable (cloudy or incomplete) observations in the same 90 days", unusable)
    if ndmi is not None:
        _fact(f, f"NDMI (moisture index) on {obs[-1][0]}", ndmi)
    if heat:
        _fact(f, "Land surface temperature of the site", heat[0], "°C")
        _fact(f, "Land surface temperature of the surrounding area", heat[1], "°C")
    else:
        _fact(f, "Surface temperature data", "not available")
    if water:
        _fact(f, "Estimated irrigation water demand over that period (estimate)", water, "m³")
    if schedule:
        _fact(f, "Scheduled irrigation over the compared days (user-entered)", schedule[0], "m³")
        _fact(f, "Scheduled minus estimated demand, percent of demand", schedule[1], "%")
    elif water:
        _fact(f, "Irrigation schedule", "not entered")
    for d, decision in decisions:
        _fact(f, f"Review decision on {d}", decision)
    if finding:
        _fact(f, "Inspection task status", "completed")
        _fact(f, "Condition observed by the inspector", finding)
    return f


CASES = [
    {
        "id": "R1-summer-turf-collapse",
        "description": "Large turf park, sharp summer NDVI drop over five observations, no schedule entered.",
        "facts": _signal(
            "Reference Park 1 (constructed)",
            "park",
            "turf",
            42000,
            [("2026-07-04", 0.21, 0.46, -5.1), ("2026-07-09", 0.19, 0.45, -5.3), ("2026-07-14", 0.17, 0.45, -5.6)],
            run_length=5,
            score=86.5,
            ndmi=-0.12,
            heat=(44.8, 47.1),
            water=2540.0,
        ),
        "expect_any": ["irrigation", "water"],
    },
    {
        "id": "R2-under-watering-schedule",
        "description": "Garden with a user-entered schedule well below estimated demand.",
        "facts": _signal(
            "Reference Garden 2 (constructed)",
            "garden",
            "mixed",
            9000,
            [("2026-06-10", 0.28, 0.41, -3.2), ("2026-06-15", 0.27, 0.40, -3.3), ("2026-06-20", 0.26, 0.40, -3.5)],
            score=58.0,
            water=640.0,
            schedule=(310.0, -51.6),
        ),
        "expect_any": ["under-water", "underwater", "insufficient", "irrigation", "water"],
    },
    {
        "id": "R3-borderline-cloudy",
        "description": "Small drop near the thresholds with many unusable (cloudy) observations.",
        "facts": _signal(
            "Reference Median 3 (constructed)",
            "median",
            "shrubs",
            6200,
            [("2026-02-02", 0.31, 0.37, -2.1), ("2026-02-12", 0.31, 0.37, -2.0), ("2026-02-17", 0.3, 0.36, -2.2)],
            score=31.0,
            usable=4,
            unusable=9,
        ),
        "expect_any": ["artefact", "artifact", "cloud", "haze", "data"],
    },
    {
        "id": "R4-construction-finding",
        "description": "Inspector recorded the area as not vegetation (works under way).",
        "facts": _signal(
            "Reference Plaza 4 (constructed)",
            "plaza",
            "turf",
            15000,
            [("2026-03-01", 0.12, 0.38, -6.0), ("2026-03-06", 0.11, 0.38, -6.2), ("2026-03-11", 0.1, 0.38, -6.4)],
            score=72.0,
            decisions=[("2026-03-13", "send for inspection")],
            finding="not vegetation",
        ),
        "expect_any": ["construction", "works", "replant", "renovation", "removal"],
    },
    {
        "id": "R5-native-planting",
        "description": "Native, low water-use planting with a moderate decline in late summer.",
        "facts": _signal(
            "Reference Park 5 (constructed)",
            "park",
            "native",
            21000,
            [("2026-08-20", 0.18, 0.24, -2.6), ("2026-08-25", 0.18, 0.24, -2.7), ("2026-08-30", 0.17, 0.24, -2.9)],
            score=44.0,
            water=380.0,
        ),
        "expect_any": ["season", "dormancy", "drought", "native", "stress"],
    },
    {
        "id": "R6-reopened",
        "description": "Signal reopened after an earlier dismissal; decline continued.",
        "facts": _signal(
            "Reference Garden 6 (constructed)",
            "garden",
            "turf",
            11000,
            [("2026-05-05", 0.24, 0.36, -3.8), ("2026-05-10", 0.23, 0.36, -4.0), ("2026-05-15", 0.22, 0.36, -4.3)],
            score=63.0,
            reopened=1,
            run_length=6,
            decisions=[("2026-04-20", "dismiss"), ("2026-05-16", "reopened")],
        ),
        "expect_any": ["irrigation", "persist", "continued", "decline"],
    },
]

OVERVIEW_CASE = {
    "id": "O1-overview",
    "description": "Overview of a 90-day period across all districts.",
    "facts": None,  # built below
}


def _overview_facts() -> list[dict]:
    f: list[dict] = []
    _fact(f, "District filter", "all districts")
    _fact(f, "Period start", "2026-08-01")
    _fact(f, "Period end", "2026-10-29")
    _fact(f, "Active green spaces", 148)
    for label, n in (
        ("Needs attention (active signal)", 9),
        ("Within seasonal range", 101),
        ("Baseline not yet available", 12),
        ("No usable satellite data", 4),
        ("Low confidence (small site)", 22),
    ):
        _fact(f, f"Green spaces: {label}", n)
    _fact(f, "Signals detected in the period", 17)
    for k, n in (("open", 6), ("under inspection", 3), ("dismissed", 3), ("closed", 5)):
        _fact(f, f"Signals detected in the period now {k}", n)
    _fact(f, "Tasks created in the period", 11)
    for k, n in (("assigned", 2), ("in progress", 1), ("completed", 7), ("cancelled", 1)):
        _fact(f, f"Tasks created in the period now {k}", n)
    _fact(f, "Overdue tasks", 2)
    for k, n in (("confirmed", 4), ("not confirmed", 1), ("inconclusive", 0)):
        _fact(f, f"Signals closed in the period with outcome {k}", n)
    _fact(f, "Confirmation rate of decided outcomes", 80.0, "%")
    return f


def _text(content) -> str:
    return json.dumps(content, ensure_ascii=False).lower()


def run_case(kind: str, case: dict) -> dict:
    out = {"id": case["id"], "kind": kind, "description": case["description"]}
    try:
        content, t_in, t_out, first = produce(kind, case["facts"])
    except AiError as exc:
        return out | {
            "ok": False,
            "error": str(exc),
            "structure": False,
            "figures_first": False,
            "figures_final": False,
            "evidence": False,
            "coverage": False,
        }
    final = validate(kind, content, case["facts"])
    evidence = (
        all(e["supporting"] and e["contradicting"] for e in content.get("explanations", []))
        if kind == "signal_brief"
        else True
    )
    coverage = any(k in _text(content.get("explanations", content)) for k in case.get("expect_any", [""]))
    return out | {
        "ok": not final,
        "structure": not [p for p in final if "explanation" in p or "checklist" in p or "missing" in p],
        "figures_first": not [p for p in first if "figure" in p or "date" in p or "fact id" in p],
        "figures_final": not [p for p in final if "figure" in p or "date" in p or "fact id" in p],
        "first_attempt_problems": first,
        "evidence": evidence,
        "coverage": coverage,
        "tokens": {"input": t_in, "output": t_out},
        "content": content,
    }


def main(out_dir: str | None) -> None:
    s = get_settings()
    if not enabled():
        print("OPENAI_API_KEY is not set: the evaluation needs the AI service and was not run.")
        sys.exit(3)
    results = [run_case("signal_brief", c) for c in CASES]
    results.append(run_case("overview_summary", OVERVIEW_CASE | {"facts": _overview_facts(), "expect_any": [""]}))
    n = len(results)
    summary = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": s.openai_model,
        "prompt_versions": [SIGNAL_PROMPT_VERSION, OVERVIEW_PROMPT_VERSION],
        "cases": n,
        "passed_validation": sum(r["ok"] for r in results),
        "figures_valid_first_attempt": sum(r["figures_first"] for r in results),
        "figures_valid_final": sum(r["figures_final"] for r in results),
        "evidence_complete": sum(r["evidence"] for r in results),
        "theme_coverage": sum(r["coverage"] for r in results),
    }
    print(json.dumps(summary, indent=2))
    for r in results:
        flag = "PASS" if r["ok"] else "FAIL"
        print(
            f"{flag}  {r['id']}  figures(first/final)={r['figures_first']}/{r['figures_final']}  "
            f"evidence={r['evidence']}  coverage={r['coverage']}  {r.get('error', '')}"
        )
    if out_dir:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "ai-eval-results.json").write_text(
            json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        with open(d / "ai-eval-rating-sheet.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["case_id", "description", "rater", "usefulness_1_to_5", "accuracy_concerns", "comments"])
            for r in results:
                w.writerow([r["id"], r["description"], "", "", "", ""])
        print(f"Wrote results and a usefulness rating sheet to {d}")
