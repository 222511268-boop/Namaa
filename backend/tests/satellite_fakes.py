"""Small synthetic Sentinel-2-like GeoTIFF scenes for pipeline tests (clearly constructed, not real data)."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import box

from app.services.satellite import Scene, SceneSourceError

EPSG = 32638
_to_utm = Transformer.from_crs(4326, EPSG, always_xy=True)
_to_wgs = Transformer.from_crs(EPSG, 4326, always_xy=True)


@dataclass
class SceneValues:
    b04: int = 1500
    b08: int = 3500
    b11: int = 2500
    scl: int = 4
    cloud_rows: int = 0  # number of top rows (10 m) set to SCL 9 (cloud high probability)


def write_scene(
    folder: Path,
    scene_id: str,
    origin_lonlat=(46.700, 24.715),
    size_px=200,
    v: SceneValues | None = None,
    baseline="05.11",
    when=datetime(2025, 6, 1, 7, 26),
    footprint=None,
) -> Scene:
    """Write B04/B08 (10 m) and B11/SCL (20 m) GeoTIFFs covering size_px x size_px 10 m pixels."""
    v = v or SceneValues()
    folder.mkdir(parents=True, exist_ok=True)
    x0, y0 = _to_utm.transform(*origin_lonlat)
    x0, y0 = round(x0 / 20) * 20, round(y0 / 20) * 20  # align both grids
    hrefs = {}
    for name, res, value, dtype in (
        ("B04", 10, v.b04, "uint16"),
        ("B08", 10, v.b08, "uint16"),
        ("B11", 20, v.b11, "uint16"),
        ("SCL", 20, v.scl, "uint8"),
    ):
        n = size_px * 10 // res
        arr = np.full((n, n), value, dtype=dtype)
        if name == "SCL" and v.cloud_rows:
            arr[: v.cloud_rows // 2, :] = 9
        path = folder / f"{scene_id}_{name}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=n,
            width=n,
            count=1,
            dtype=dtype,
            crs=f"EPSG:{EPSG}",
            transform=from_origin(x0, y0, res, res),
        ) as dst:
            dst.write(arr, 1)
        hrefs[name] = str(path)
    # True-colour asset for evidence chips: 3 x uint8 at 10 m (constructed values).
    n = size_px
    vis = folder / f"{scene_id}_visual.tif"
    rgb = np.stack([np.full((n, n), c, dtype="uint8") for c in (60, 120, 50)])
    with rasterio.open(
        vis,
        "w",
        driver="GTiff",
        height=n,
        width=n,
        count=3,
        dtype="uint8",
        crs=f"EPSG:{EPSG}",
        transform=from_origin(x0, y0, 10, 10),
    ) as dst:
        dst.write(rgb)
    hrefs["visual"] = str(vis)
    if footprint is None:
        xmax, ymin = x0 + size_px * 10, y0 - size_px * 10
        (lon0, lat1), (lon1, lat0) = _to_wgs.transform(x0, y0), _to_wgs.transform(xmax, ymin)
        footprint = box(lon0, lat0, lon1, lat1)
    return Scene(
        id=scene_id,
        acquired_at=when,
        platform="Sentinel-2B",
        processing_baseline=baseline,
        epsg=EPSG,
        footprint=footprint,
        hrefs=hrefs,
    )


class FakeSource:
    def __init__(self, scenes: list[Scene], fail_search: bool = False):
        self.scenes = scenes
        self.fail_search = fail_search
        self.searches = []

    def search(self, bbox, start, end):
        self.searches.append((bbox, start, end))
        if self.fail_search:
            raise SceneSourceError("The satellite catalogue could not be searched: simulated outage")
        return self.scenes

    def signed_hrefs(self, scene):
        return scene.hrefs

    def get_scene(self, scene_id):
        for sc in self.scenes:
            if sc.id == scene_id:
                return sc
        raise SceneSourceError(f"The scene {scene_id} was not found in the catalogue.")


def reference_stats(scene: Scene, site_geom_wgs84, v: SceneValues, offset: int):
    """Independent calculation: test every 10 m pixel centre against the polygon with shapely."""
    from shapely.geometry import Point
    from shapely.ops import transform

    with rasterio.open(scene.hrefs["B04"]) as src:
        t, h, w = src.transform, src.height, src.width
    poly = transform(_to_utm.transform, site_geom_wgs84)
    minx, miny, maxx, maxy = poly.bounds
    inside = valid = 0
    for row in range(h):
        for col in range(w):
            x, y = t.c + (col + 0.5) * t.a, t.f + (row + 0.5) * t.e
            if not (minx <= x <= maxx and miny <= y <= maxy) or not poly.contains(Point(x, y)):
                continue
            inside += 1
            if row >= v.cloud_rows:  # SCL row index at 20 m = row // 2; cloud covers rows < cloud_rows
                valid += 1
    red, nir, swir = ((v.b04 + offset) / 1e4, (v.b08 + offset) / 1e4, (v.b11 + offset) / 1e4)
    return {"inside": inside, "valid": valid, "ndvi": (nir - red) / (nir + red), "ndmi": (nir - swir) / (nir + swir)}


__all__ = ["FakeSource", "SceneValues", "write_scene", "reference_stats", "SceneSourceError"]
