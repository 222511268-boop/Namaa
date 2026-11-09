"""Land surface temperature from Landsat 8/9 Collection 2 Level-2 (US19-US20).

For each scene:
- Surface temperature band ST_B10 (Planetary Computer asset "lwir11"): kelvin = DN x 0.00341802 + 149.0;
  degrees Celsius = kelvin - 273.15. DN 0 is no data. The thermal sensor's native resolution is 100 m; USGS
  delivers it resampled to 30 m.
- Pixel quality ("qa_pixel"): pixels flagged as fill (bit 0), dilated cloud (1), cirrus (2), cloud (3) or cloud
  shadow (4) are excluded.
- Site value: mean over clear pixels inside the boundary (pixels touching the boundary for sites smaller than a
  pixel). Surrounding-area value: mean over clear pixels in a ring of `lst_surround_m` around the site.
- Map layer: the pilot area reprojected to WGS84 at 0.0005 degrees (about 50 m) and coloured on a fixed scale.

Landsat data courtesy of the U.S. Geological Survey, accessed through the Microsoft Planetary Computer.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date

import numpy as np
import rasterio
from geoalchemy2.shape import to_shape
from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import transform as window_transform
from shapely.geometry import box
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import LstLayer, LstObservation, ProcessingRun, RunKind, RunStatus, Site, SiteStatus
from app.services.media import media_path
from app.services.satellite import Scene, SceneSourceError, _window_for_bounds, project_polygon

log = logging.getLogger("namaa.heat")

ATTRIBUTION = "Landsat data courtesy of the U.S. Geological Survey"
SOURCE_RESOLUTION = "Landsat thermal band: 100 m native resolution, delivered at 30 m"
ST_SCALE, ST_OFFSET = 0.00341802, 149.0
QA_EXCLUDE = 0b11111  # fill, dilated cloud, cirrus, cloud, cloud shadow
LAYER_DEG = 0.0005
MIN_SITE_SHARE = 0.5  # share of the site's pixels that must be clear for a usable value
# Colour scale of the map layer and its legend: (degrees Celsius, hex colour), light to dark.
RAMP = [
    (15.0, "#fef3c7"),
    (25.0, "#fcd34d"),
    (35.0, "#f59e0b"),
    (45.0, "#ea580c"),
    (55.0, "#b91c1c"),
    (65.0, "#6b0f1a"),
]


def dn_to_celsius(dn: np.ndarray) -> np.ndarray:
    return dn.astype(np.float64) * ST_SCALE + ST_OFFSET - 273.15


def clear_mask(st: np.ndarray, qa: np.ndarray) -> np.ndarray:
    return (st != 0) & ((qa & QA_EXCLUDE) == 0)


@dataclass
class LstStats:
    site_c: float | None
    surround_c: float | None
    site_pixels: int
    surround_pixels: int
    site_total: int

    @property
    def valid_share(self) -> float:
        return self.site_pixels / self.site_total if self.site_total else 0.0

    @property
    def usable(self) -> bool:
        return self.site_c is not None and self.valid_share >= MIN_SITE_SHARE


def compute_lst_stats(celsius: np.ndarray, clear: np.ndarray, inside: np.ndarray, ring: np.ndarray) -> LstStats:
    site_ok = inside & clear
    ring_ok = ring & clear
    n_site, n_ring = int(site_ok.sum()), int(ring_ok.sum())
    return LstStats(
        site_c=float(celsius[site_ok].mean()) if n_site else None,
        surround_c=float(celsius[ring_ok].mean()) if n_ring else None,
        site_pixels=n_site,
        surround_pixels=n_ring,
        site_total=int(inside.sum()),
    )


def colourise(celsius: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """RGBA image on the fixed RAMP scale; invalid pixels are transparent."""
    temps = np.array([t for t, _ in RAMP])
    cols = np.array([[int(h[i : i + 2], 16) for i in (1, 3, 5)] for _, h in RAMP], dtype=np.float64)
    v = np.clip(celsius, temps[0], temps[-1])
    rgba = np.zeros((*celsius.shape, 4), dtype=np.uint8)
    for ch in range(3):
        rgba[..., ch] = np.interp(v, temps, cols[:, ch]).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0)
    return rgba


class LstReader:
    """Keeps the thermal and quality assets of one scene open while sites are read."""

    def __init__(self, hrefs: dict[str, str], scene: Scene):
        self.hrefs = hrefs
        self.scene = scene
        self._st = self._qa = None

    def __enter__(self) -> "LstReader":
        self._st = rasterio.open(self.hrefs["lwir11"])
        try:
            self._qa = rasterio.open(self.hrefs["qa_pixel"])
        except Exception:
            self._st.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        for src in (self._st, self._qa):
            if src is not None:
                src.close()

    def site_stats(self, site_geom_wgs84) -> LstStats:
        s = get_settings()
        site_utm = project_polygon(site_geom_wgs84, self.scene.epsg)
        outer = site_utm.buffer(s.lst_surround_m)
        win = _window_for_bounds(self._st, outer.bounds)
        st = self._st.read(1, window=win)
        qa = self._qa.read(1, window=win)
        tr = window_transform(win, self._st.transform)
        shape = st.shape
        inside = geometry_mask([site_utm], out_shape=shape, transform=tr, invert=True)
        if not inside.any():  # site smaller than a pixel: use the pixels it touches
            inside = geometry_mask([site_utm], out_shape=shape, transform=tr, invert=True, all_touched=True)
        within_outer = geometry_mask([outer], out_shape=shape, transform=tr, invert=True)
        ring = within_outer & ~geometry_mask([site_utm], out_shape=shape, transform=tr, invert=True, all_touched=True)
        return compute_lst_stats(dn_to_celsius(st), clear_mask(st, qa), inside, ring)

    def render_layer(self, bbox: tuple[float, float, float, float]):
        """Pilot-area layer in WGS84: (RGBA array, [w, s, e, n], min °C, max °C, clear share)."""
        w, s_, e, n = bbox
        width, height = round((e - w) / LAYER_DEG), round((n - s_) / LAYER_DEG)
        dst_tr = from_origin(w, n, LAYER_DEG, LAYER_DEG)
        utm_bounds = transform_bounds("EPSG:4326", self._st.crs, w, s_, e, n)
        win = _window_for_bounds(self._st, utm_bounds)
        out = {}
        for key, src in (("st", self._st), ("qa", self._qa)):
            arr = src.read(1, window=win)
            dst = np.zeros((height, width), dtype=arr.dtype)
            reproject(
                source=arr,
                destination=dst,
                src_transform=window_transform(win, src.transform),
                src_crs=src.crs,
                dst_transform=dst_tr,
                dst_crs="EPSG:4326",
                resampling=Resampling.nearest,
                src_nodata=0 if key == "st" else 1,
                dst_nodata=0 if key == "st" else 1,
            )
            out[key] = dst
        valid = clear_mask(out["st"], out["qa"])
        celsius = dn_to_celsius(out["st"])
        share = float(valid.mean())
        lo = float(celsius[valid].min()) if share else 0.0
        hi = float(celsius[valid].max()) if share else 0.0
        return colourise(celsius, valid), [w, s_, e, n], lo, hi, share


class LandsatSource:
    """Landsat 8/9 Collection 2 Level-2 scenes from the Microsoft Planetary Computer STAC API."""

    def __init__(self, api_url: str, collection: str, max_cloud: float):
        self.api_url = api_url
        self.collection = collection
        self.max_cloud = max_cloud

    def search(self, bbox, start, end) -> list[Scene]:
        import pystac_client
        from shapely.geometry import shape

        try:
            client = pystac_client.Client.open(self.api_url)
            items = list(
                client.search(
                    collections=[self.collection],
                    bbox=list(bbox),
                    datetime=f"{start}/{end}",
                    query={"eo:cloud_cover": {"lt": self.max_cloud}, "platform": {"in": ["landsat-8", "landsat-9"]}},
                ).items()
            )
        except Exception as exc:
            raise SceneSourceError(f"The Landsat catalogue could not be searched: {exc}") from exc
        scenes = []
        for it in items:
            if "lwir11" not in it.assets or "qa_pixel" not in it.assets:
                continue
            p = it.properties
            scenes.append(
                Scene(
                    id=it.id,
                    acquired_at=it.datetime,
                    platform=p.get("platform", "landsat"),
                    processing_baseline="",
                    epsg=int(p.get("proj:epsg") or p.get("proj:code", "EPSG:0").split(":")[1]),
                    footprint=shape(it.geometry),
                    hrefs={k: it.assets[k].href for k in ("lwir11", "qa_pixel")},
                )
            )
        scenes.sort(key=lambda sc: sc.acquired_at)
        return scenes

    def signed_hrefs(self, scene: Scene) -> dict[str, str]:
        import planetary_computer

        try:
            return {k: planetary_computer.sign(v) for k, v in scene.hrefs.items()}
        except Exception as exc:
            raise SceneSourceError(f"Image access could not be authorised: {exc}") from exc


# ---------------------------------------------------------------- runs


def queue_lst_run(db: Session, start: date, end: date, user_id) -> ProcessingRun:
    run = ProcessingRun(
        kind=RunKind.landsat_lst,
        status=RunStatus.queued,
        params={"start_date": start.isoformat(), "end_date": end.isoformat(), "site_ids": None},
        requested_by=user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _store(db: Session, run, site, scene, stats: LstStats) -> bool:
    day = scene.acquired_at.date()
    obs = db.scalar(
        select(LstObservation).where(
            LstObservation.site_id == site.id,
            LstObservation.acquired_on == day,
            LstObservation.boundary_version == site.boundary_version,
        )
    )
    if obs is not None and obs.site_pixels >= stats.site_pixels:
        return False
    if obs is None:
        obs = LstObservation(site_id=site.id, acquired_on=day, boundary_version=site.boundary_version)
        db.add(obs)
    obs.run_id = run.id
    obs.scene_id = scene.id
    obs.platform = scene.platform
    obs.site_c = round(stats.site_c, 2) if stats.site_c is not None else None
    obs.surround_c = round(stats.surround_c, 2) if stats.surround_c is not None else None
    obs.site_pixels, obs.surround_pixels = stats.site_pixels, stats.surround_pixels
    obs.valid_share = round(stats.valid_share, 4)
    obs.usable = stats.usable
    return True


def _store_layer(db: Session, reader: LstReader, scene: Scene) -> bool:
    if db.scalar(select(LstLayer.id).where(LstLayer.scene_id == scene.id)):
        return False
    rgba, bounds, lo, hi, share = reader.render_layer(get_settings().pilot_bbox)
    if share < 0.05:  # scene barely covers the pilot area or is mostly cloud
        return False
    name = f"{uuid.uuid4().hex}.png"
    Image.fromarray(rgba, "RGBA").save(media_path("heat", name), "PNG", optimize=True)
    db.add(
        LstLayer(
            scene_id=scene.id,
            platform=scene.platform,
            acquired_on=scene.acquired_at.date(),
            image=name,
            bounds=bounds,
            min_c=round(lo, 1),
            max_c=round(hi, 1),
            valid_share=round(share, 4),
        )
    )
    return True


def execute_lst_run(db: Session, run: ProcessingRun, source: LandsatSource) -> ProcessingRun:
    from app.services.processing import _finish, _note

    s = get_settings()
    params = run.params or {}
    run.scenes_found = run.scenes_processed = run.items_written = run.items_skipped = 0
    sites = list(db.scalars(select(Site).where(Site.status == SiteStatus.active)))
    shapes = {site.id: to_shape(site.geom) for site in sites}
    try:
        scenes = source.search(s.pilot_bbox, params["start_date"], params["end_date"])
    except SceneSourceError as exc:
        return _finish(db, run, RunStatus.failed, str(exc))
    run.scenes_found = len(scenes)
    db.commit()
    pilot = box(*s.pilot_bbox)
    failures = layers = 0
    for scene in scenes:
        try:
            with LstReader(source.signed_hrefs(scene), scene) as reader:
                for site in sites:
                    if not scene.footprint.contains(shapes[site.id]):
                        continue
                    if _store(db, run, site, scene, reader.site_stats(shapes[site.id])):
                        run.items_written += 1
                    else:
                        run.items_skipped += 1
                if scene.footprint.intersects(pilot) and _store_layer(db, reader, scene):
                    layers += 1
            run.scenes_processed += 1
            db.commit()
        except Exception as exc:
            db.rollback()
            failures += 1
            log.warning("Landsat scene %s failed: %s", scene.id, exc)
            _note(run, f"Scene {scene.id} could not be processed: {exc}")
            db.commit()
    _note(run, f"{layers} surface temperature map layers created. {ATTRIBUTION}.")
    if failures:
        return _finish(
            db,
            run,
            RunStatus.failed,
            f"{failures} of {len(scenes)} scenes could not be processed. Completed scenes were saved.",
        )
    return _finish(db, run, RunStatus.succeeded, None)


def latest_layer(db: Session) -> LstLayer | None:
    return db.scalar(select(LstLayer).order_by(LstLayer.acquired_on.desc(), LstLayer.valid_share.desc()))
