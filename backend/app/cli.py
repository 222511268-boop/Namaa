"""Setup commands.

python -m app.cli load-districts     Load Riyadh district boundaries from the bundled GeoJSON file.
python -m app.cli fetch-districts    Re-download district boundaries from OpenStreetMap into that file.
python -m app.cli bootstrap-admin    Create the first administrator from environment variables.
python -m app.cli analyse            Recalculate baselines and detection for all active sites, then evidence images.
python -m app.cli labelling-template FILE   Write a CSV for labelling sites (detection evaluation).
python -m app.cli evaluate-detection FILE   Precision and recall of detection against a labelled CSV.
python -m app.cli ai-eval [FILE]     Evaluate AI briefs against the reference signals (needs OPENAI_API_KEY).
"""

import json
import sys
from datetime import UTC, datetime

from shapely.geometry import mapping

from app.config import get_settings
from app.db import SessionLocal
from app.services import osm
from app.services.geometry import as_multipolygon


def fetch_districts() -> None:
    s = get_settings()
    data = osm.run_query(osm.districts_query(s.pilot_bbox))
    features = []
    for f in osm.parse_elements(data).features:
        if f.geom is None:
            print(f"skipped {f.ref}: {f.problem}")
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "osm_id": int(f.ref.split("/")[1]),
                    "name_en": f.tags.get("name:en"),
                    "name_ar": f.tags.get("name:ar") or f.tags.get("name"),
                },
                "geometry": mapping(as_multipolygon(f.geom)),
            }
        )
    fc = {
        "type": "FeatureCollection",
        "attribution": osm.OSM_ATTRIBUTION,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "query": "relation[boundary=administrative][admin_level=10] within the pilot bounding box",
        "features": features,
    }
    with open(s.districts_file, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False)
    print(f"Saved {len(features)} districts to {s.districts_file}")


def load_districts() -> None:
    from app.services.sites import load_districts_geojson

    with SessionLocal() as db:
        n = load_districts_geojson(db, get_settings().districts_file)
    print(f"Loaded {n} districts")


def bootstrap_admin() -> None:
    from app.bootstrap import ensure_bootstrap_admin

    with SessionLocal() as db:
        user = ensure_bootstrap_admin(db)
    print(f"Created administrator {user.email}" if user else "An administrator already exists (or variables unset).")


def analyse() -> None:
    from app.services.analysis import analyse_sites
    from app.services.imagery import generate_signal_images
    from app.services.satellite import PlanetaryComputerSource

    s = get_settings()
    with SessionLocal() as db:
        summary = analyse_sites(db)
        images = generate_signal_images(
            db,
            PlanetaryComputerSource(s.stac_api_url, s.stac_collection, s.scene_max_cloud_cover),
            summary.changed_signal_ids,
        )
    print(
        f"Evaluated {summary.sites_evaluated} sites: {summary.signals_created} new, {summary.signals_updated} updated, "
        f"{summary.signals_reopened} reopened signals; {images} evidence images; not raised: {summary.skipped}"
    )


def labelling_template() -> None:
    from app.services.evaluation import write_template

    with SessionLocal() as db:
        n = write_template(db, sys.argv[2])
    print(f"Wrote {n} sites to {sys.argv[2]}. Fill 'label' with decline, no_decline or unsure.")


def evaluate_detection() -> None:
    from app.services.evaluation import evaluate_file

    with SessionLocal() as db:
        r = evaluate_file(db, sys.argv[2])
    fmt = lambda v: "n/a" if v is None else f"{v:.0%}"  # noqa: E731
    print(f"TP={r.tp} FP={r.fp} FN={r.fn} TN={r.tn} unsure={r.unsure} unknown_sites={r.unknown_sites}")
    print(f"Precision {fmt(r.precision)}  Recall {fmt(r.recall)}  (n labelled = {r.tp + r.fp + r.fn + r.tn})")


def ai_eval() -> None:
    from app.services.ai_eval import main as run_eval

    run_eval(sys.argv[2] if len(sys.argv) > 2 else None)


COMMANDS = {
    "fetch-districts": fetch_districts,
    "load-districts": load_districts,
    "bootstrap-admin": bootstrap_admin,
    "analyse": analyse,
    "labelling-template": labelling_template,
    "evaluate-detection": evaluate_detection,
    "ai-eval": ai_eval,
}

if __name__ == "__main__":
    needs_file = {"labelling-template", "evaluate-detection"}
    optional_file = {"ai-eval"}
    if (
        len(sys.argv) < 2
        or sys.argv[1] not in COMMANDS
        or (sys.argv[1] not in optional_file and (sys.argv[1] in needs_file) != (len(sys.argv) == 3))
    ):
        print(__doc__)
        sys.exit(2)
    COMMANDS[sys.argv[1]]()
