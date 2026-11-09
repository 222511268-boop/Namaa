"""Before and after image chips for signal evidence (US12).

A chip is a window of the Sentinel-2 true-colour ("visual", 10 m) asset around the site with a 40 % margin
(at least 300 m across), upscaled to 384 px, with the site outline drawn on it. Contains modified Copernicus
Sentinel data.
"""

import logging
import uuid

import numpy as np
import rasterio
from geoalchemy2.shape import to_shape
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from app.models import Observation, Signal
from app.services.media import media_path
from app.services.satellite import SceneSource, _window_for_bounds, project_polygon

log = logging.getLogger("namaa.imagery")
CHIP_PX = 384
MARGIN = 0.4
MIN_EXTENT_M = 300.0


def _chip_bounds(site_utm) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = site_utm.bounds
    w, h = maxx - minx, maxy - miny
    side = max(w, h) * (1 + 2 * MARGIN)
    side = max(side, MIN_EXTENT_M)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    return cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2


def render_chip(visual_href: str, epsg: int, site_geom_wgs84) -> Image.Image:
    site_utm = project_polygon(site_geom_wgs84, epsg)
    bounds = _chip_bounds(site_utm)
    with rasterio.open(visual_href) as src:
        win = _window_for_bounds(src, bounds, pad=0)
        rgb = src.read([1, 2, 3], window=win)
        transform = src.window_transform(win)
    img = Image.fromarray(np.transpose(rgb, (1, 2, 0)).astype(np.uint8), "RGB")
    scale = CHIP_PX / max(img.width, img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.Resampling.BICUBIC)

    def to_px(x: float, y: float) -> tuple[float, float]:
        col = (x - transform.c) / transform.a
        row = (y - transform.f) / transform.e
        return col * scale, row * scale

    draw = ImageDraw.Draw(img)
    polys = getattr(site_utm, "geoms", [site_utm])
    for poly in polys:
        draw.line([to_px(x, y) for x, y in poly.exterior.coords], fill=(255, 214, 10), width=3)
    return img


def chip_for_observation(db: Session, source: SceneSource, obs_id, site_geom) -> str | None:
    """Create a chip for an observation's scene; returns the stored file name or None on failure."""
    obs = db.get(Observation, obs_id)
    if obs is None:
        return None
    try:
        scene = source.get_scene(obs.scene_id)
        hrefs = source.signed_hrefs(scene)
        if "visual" not in hrefs:
            return None
        img = render_chip(hrefs["visual"], scene.epsg, site_geom)
        name = f"{uuid.uuid4().hex}.png"
        img.save(media_path("chips", name), "PNG", optimize=True)
        return name
    except Exception as exc:  # evidence images are helpful but never block a signal
        log.warning("Image chip for observation %s failed: %s", obs_id, exc)
        return None


def generate_signal_images(db: Session, source: SceneSource, signal_ids: list) -> int:
    """Create missing or outdated before/after chips for the given signals. Returns chips created."""
    created = 0
    for sid in signal_ids:
        signal = db.get(Signal, sid)
        if signal is None:
            continue
        geom = to_shape(signal.site.geom)
        evidence = signal.evidence or {}
        if signal.before_obs_id and not signal.before_image:
            signal.before_image = chip_for_observation(db, source, signal.before_obs_id, geom)
            created += bool(signal.before_image)
        if signal.after_obs_id and evidence.get("after_image_obs") != str(signal.after_obs_id):
            # Never present a previous acquisition under the newer observation's date after a failed download.
            signal.after_image = None
            name = chip_for_observation(db, source, signal.after_obs_id, geom)
            if name:
                signal.after_image = name
                signal.evidence = evidence | {"after_image_obs": str(signal.after_obs_id)}
                created += 1
        db.commit()
    return created
