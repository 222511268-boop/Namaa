"""Sentinel-2 Level-2A access and per-site vegetation index calculation.

Pipeline for one scene and one site:
1. Project the site polygon to the scene CRS (UTM).
2. Read 10 m B04 (red) and B08 (NIR) windows covering the polygon; read 20 m B11 (SWIR) and SCL
   (scene classification) and resample them to the 10 m grid by nearest neighbour.
3. Convert digital numbers to reflectance: (DN + offset) / 10000, offset = -1000 for processing
   baseline 04.00 and later (ESA change of January 2022), otherwise 0.
4. Keep pixels whose centre is inside the polygon, whose SCL class is valid, and whose bands are not
   no-data (DN 0). Compute NDVI and NDMI per pixel and summarise mean and standard deviation.

Contains modified Copernicus Sentinel data.
"""

import math
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.warp import reproject
from rasterio.windows import Window
from rasterio.windows import transform as window_transform
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import transform as shp_transform

# SCL classes accepted as clear observations: 4 vegetation, 5 not vegetated, 6 water, 7 unclassified.
# Rejected: 0 no data, 1 saturated/defective, 2 dark area, 3 cloud shadow, 8/9 cloud medium/high
# probability, 10 thin cirrus, 11 snow/ice.
VALID_SCL = np.array([4, 5, 6, 7], dtype=np.uint8)
ASSETS = ("B04", "B08", "B11", "SCL")

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.tiff")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")


class SceneSourceError(RuntimeError):
    pass


@dataclass
class Scene:
    id: str
    acquired_at: datetime
    platform: str
    processing_baseline: str
    epsg: int
    footprint: Polygon | MultiPolygon  # valid-data footprint in WGS84
    hrefs: dict[str, str] = field(default_factory=dict)


class SceneSource(Protocol):
    def search(self, bbox: tuple[float, float, float, float], start: str, end: str) -> list[Scene]: ...

    def signed_hrefs(self, scene: Scene) -> dict[str, str]: ...

    def get_scene(self, scene_id: str) -> Scene: ...


@dataclass
class SiteStats:
    ndvi_mean: float | None
    ndvi_std: float | None
    ndmi_mean: float | None
    ndmi_std: float | None
    valid_pixels: int
    total_pixels: int

    @property
    def valid_share(self) -> float:
        return self.valid_pixels / self.total_pixels if self.total_pixels else 0.0

    def usable(self, min_share: float, min_pixels: int) -> bool:
        return self.valid_pixels >= min_pixels and self.valid_share >= min_share


# ---------------------------------------------------------------- pure calculations


def reflectance_offset(processing_baseline: str) -> int:
    """BOA_ADD_OFFSET for Sentinel-2 L2A: -1000 from processing baseline 04.00 onwards."""
    try:
        major = float(processing_baseline)
    except (TypeError, ValueError):
        return -1000  # all current products are baseline 05.xx
    return -1000 if major >= 4.0 else 0


def compute_site_stats(
    b04: np.ndarray, b08: np.ndarray, b11: np.ndarray, scl: np.ndarray, inside: np.ndarray, offset: int
) -> SiteStats:
    """Summarise NDVI and NDMI over valid pixels inside the site polygon.

    All arrays share the same 10 m grid. `inside` is True for pixels whose centre lies in the polygon.
    """
    total = int(inside.sum())
    nodata = (b04 == 0) | (b08 == 0) | (b11 == 0)
    valid = inside & np.isin(scl, VALID_SCL) & ~nodata

    red = (b04.astype(np.float64) + offset) / 10000.0
    nir = (b08.astype(np.float64) + offset) / 10000.0
    swir = (b11.astype(np.float64) + offset) / 10000.0
    # Reflectance can be <= 0 after the offset for very dark pixels; exclude zero denominators.
    nd_den = nir + red
    nm_den = nir + swir
    valid &= (nd_den > 0) & (nm_den > 0)
    n = int(valid.sum())
    if n == 0:
        return SiteStats(None, None, None, None, 0, total)

    ndvi = (nir[valid] - red[valid]) / nd_den[valid]
    ndmi = (nir[valid] - swir[valid]) / nm_den[valid]
    return SiteStats(
        ndvi_mean=float(ndvi.mean()),
        ndvi_std=float(ndvi.std()),
        ndmi_mean=float(ndmi.mean()),
        ndmi_std=float(ndmi.std()),
        valid_pixels=n,
        total_pixels=total,
    )


# ---------------------------------------------------------------- raster reading


def project_polygon(geom, epsg: int):
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    return shp_transform(tr.transform, geom)


def _window_for_bounds(src, bounds, pad: int = 1) -> Window:
    minx, miny, maxx, maxy = bounds
    t = src.transform
    col0 = math.floor((minx - t.c) / t.a) - pad
    col1 = math.ceil((maxx - t.c) / t.a) + pad
    row0 = math.floor((maxy - t.f) / t.e) - pad
    row1 = math.ceil((miny - t.f) / t.e) + pad
    col0, row0 = max(col0, 0), max(row0, 0)
    col1, row1 = min(col1, src.width), min(row1, src.height)
    if col1 <= col0 or row1 <= row0:
        raise SceneSourceError("Site lies outside the image extent.")
    return Window(col0, row0, col1 - col0, row1 - row0)


class SceneReader:
    """Keeps the four assets of one scene open while every site is read from them.

    Opening a remote COG costs a header request, so a scene is opened once rather than once per site.
    """

    def __init__(self, hrefs: dict[str, str], scene: Scene):
        self.hrefs = hrefs
        self.scene = scene
        self.offset = reflectance_offset(scene.processing_baseline)
        self._src: dict[str, rasterio.io.DatasetReader] = {}

    def __enter__(self) -> "SceneReader":
        try:
            for key in ASSETS:
                self._src[key] = rasterio.open(self.hrefs[key])
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        for src in self._src.values():
            src.close()
        self._src.clear()

    def read_site_arrays(self, site_utm) -> dict[str, np.ndarray]:
        """Read the four assets for the site's bounding window on the 10 m grid."""
        src10 = self._src["B04"]
        win = _window_for_bounds(src10, site_utm.bounds)
        dst_transform = window_transform(win, src10.transform)
        shape10 = (int(win.height), int(win.width))
        out = {"B04": src10.read(1, window=win), "B08": self._src["B08"].read(1, window=win)}
        for key in ("B11", "SCL"):
            src20 = self._src[key]
            win20 = _window_for_bounds(src20, site_utm.bounds, pad=2)
            arr20 = src20.read(1, window=win20)
            dst = np.zeros(shape10, dtype=arr20.dtype)
            reproject(
                source=arr20,
                destination=dst,
                src_transform=window_transform(win20, src20.transform),
                src_crs=src20.crs,
                dst_transform=dst_transform,
                dst_crs=src10.crs,
                resampling=Resampling.nearest,
            )
            out[key] = dst
        out["inside"] = geometry_mask([site_utm], out_shape=shape10, transform=dst_transform, invert=True)
        return out

    def site_stats(self, site_geom_wgs84) -> SiteStats:
        a = self.read_site_arrays(project_polygon(site_geom_wgs84, self.scene.epsg))
        return compute_site_stats(a["B04"], a["B08"], a["B11"], a["SCL"], a["inside"], self.offset)


# ---------------------------------------------------------------- Planetary Computer source


class PlanetaryComputerSource:
    """Sentinel-2 L2A scenes from the Microsoft Planetary Computer STAC API (anonymous access)."""

    def __init__(self, api_url: str, collection: str, max_cloud: float):
        self.api_url = api_url
        self.collection = collection
        self.max_cloud = max_cloud

    def search(self, bbox, start, end) -> list[Scene]:
        import pystac_client

        try:
            client = pystac_client.Client.open(self.api_url)
            search = client.search(
                collections=[self.collection],
                bbox=list(bbox),
                datetime=f"{start}/{end}",
                query={"eo:cloud_cover": {"lt": self.max_cloud}},
            )
            items = list(search.items())
        except Exception as exc:  # network or API errors
            raise SceneSourceError(f"The satellite catalogue could not be searched: {exc}") from exc
        scenes = [self._to_scene(it) for it in items]
        scenes.sort(key=lambda s: s.acquired_at)
        return scenes

    def get_scene(self, scene_id: str) -> Scene:
        import pystac_client

        try:
            client = pystac_client.Client.open(self.api_url)
            item = client.get_collection(self.collection).get_item(scene_id)
        except Exception as exc:
            raise SceneSourceError(f"The scene {scene_id} could not be retrieved: {exc}") from exc
        if item is None:
            raise SceneSourceError(f"The scene {scene_id} was not found in the catalogue.")
        return self._to_scene(item)

    @staticmethod
    def _to_scene(it) -> Scene:
        p = it.properties
        return Scene(
            id=it.id,
            acquired_at=it.datetime,
            platform=p.get("platform", "Sentinel-2"),
            processing_baseline=str(p.get("s2:processing_baseline", "")),
            epsg=int(p.get("proj:epsg") or p.get("proj:code", "EPSG:0").split(":")[1]),
            footprint=shape(it.geometry),
            # "visual" (true colour) is used for evidence image chips, not for index calculation.
            hrefs={k: it.assets[k].href for k in (*ASSETS, "visual") if k in it.assets},
        )

    def signed_hrefs(self, scene: Scene) -> dict[str, str]:
        import planetary_computer

        try:
            return {k: planetary_computer.sign(v) for k, v in scene.hrefs.items()}
        except Exception as exc:
            raise SceneSourceError(f"Image access could not be authorised: {exc}") from exc
