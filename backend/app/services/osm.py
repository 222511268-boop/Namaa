"""OpenStreetMap access through the Overpass API and conversion of OSM elements to polygons.

OSM data is (c) OpenStreetMap contributors and available under the ODbL.
"""

import time
from dataclasses import dataclass, field

import httpx
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from app.config import get_settings

OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"


class OverpassError(RuntimeError):
    pass


@dataclass
class OsmFeature:
    ref: str  # e.g. "way/123" or "relation/456"
    tags: dict
    geom: Polygon | MultiPolygon | None
    problem: str | None = None  # why the geometry could not be built

    @property
    def name(self) -> str | None:
        return self.tags.get("name:en") or self.tags.get("name")

    @property
    def name_ar(self) -> str | None:
        return self.tags.get("name:ar") or (self.tags.get("name") if _is_arabic(self.tags.get("name")) else None)


@dataclass
class ParsedResponse:
    features: list[OsmFeature] = field(default_factory=list)


def _is_arabic(text: str | None) -> bool:
    return bool(text) and any("؀" <= ch <= "ۿ" for ch in text)


_TRANSIENT = {502, 503, 504}


def _query_endpoint(url: str, query: str) -> dict:
    s = get_settings()
    try:
        resp = httpx.post(
            url, data={"data": query}, headers={"User-Agent": s.http_user_agent}, timeout=s.overpass_timeout_s
        )
    except httpx.HTTPError as exc:
        raise OverpassError("OpenStreetMap could not be reached. Please try again later.") from exc
    if resp.status_code == 429:
        raise OverpassError("OpenStreetMap is busy (rate limit reached). Please wait a minute and try again.")
    if resp.status_code != 200:
        raise OverpassError(f"OpenStreetMap returned an error (HTTP {resp.status_code}). Please try again later.")
    try:
        data = resp.json()
    except ValueError as exc:
        raise OverpassError("OpenStreetMap returned an unreadable response.") from exc
    # Overpass reports timeouts and memory limits in a 'remark' while still answering 200 with a
    # partial result; a partial result must never be imported as if it were complete.
    remark = data.get("remark") or ""
    if "error" in remark.lower():
        raise OverpassError(
            "OpenStreetMap could not complete the request (server limit reached). Please try again later."
        )
    return data


def run_query(query: str) -> dict:
    """Run an Overpass query, retrying transient failures and falling back to other public instances."""
    s = get_settings()
    last: OverpassError | None = None
    for url in [s.overpass_url, *s.overpass_fallback_urls]:
        for attempt in range(s.overpass_attempts_per_endpoint):
            try:
                return _query_endpoint(url, query)
            except OverpassError as exc:
                last = exc
                if attempt + 1 < s.overpass_attempts_per_endpoint:
                    time.sleep(s.overpass_retry_delay_s)
    raise last or OverpassError("OpenStreetMap could not be reached. Please try again later.")


def parks_query(bbox: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f'[out:json][timeout:90];(way["leisure"="park"]({b});relation["leisure"="park"]({b}););out geom;'


def districts_query(bbox: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    b = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f'[out:json][timeout:120];relation["boundary"="administrative"]["admin_level"="10"]({b});out geom;'


def _coords(geometry: list[dict]) -> list[tuple[float, float]]:
    return [(p["lon"], p["lat"]) for p in geometry if p is not None]


def _way_polygon(el: dict) -> tuple[Polygon | None, str | None]:
    pts = _coords(el.get("geometry") or [])
    if len(pts) < 4 or pts[0] != pts[-1]:
        return None, "Not a closed area (open way)"
    if len(set(pts)) < 3:
        return None, "Fewer than three distinct points"
    poly = Polygon(pts)
    if not poly.is_valid:
        return None, "Invalid geometry (self-intersecting)"
    if poly.area <= 0:
        return None, "Zero area"
    return poly, None


def _relation_polygon(el: dict) -> tuple[MultiPolygon | None, str | None]:
    if el.get("tags", {}).get("type") not in (None, "multipolygon", "boundary"):
        return None, "Relation is not a multipolygon"
    outers, inners = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        line = LineString(_coords(m["geometry"]))
        (inners if m.get("role") == "inner" else outers).append(line)
    if not outers:
        return None, "Relation has no outer boundary"
    outer_polys = list(polygonize(unary_union(outers)))
    if not outer_polys:
        return None, "Outer boundary is not closed"
    shape = unary_union(outer_polys)
    if inners:
        holes = list(polygonize(unary_union(inners)))
        if holes:
            shape = shape.difference(unary_union(holes))
    if isinstance(shape, Polygon):
        shape = MultiPolygon([shape])
    if not isinstance(shape, MultiPolygon) or not shape.is_valid or shape.area <= 0:
        return None, "Invalid geometry"
    return shape, None


def parse_elements(data: dict) -> ParsedResponse:
    out = ParsedResponse()
    for el in data.get("elements", []):
        kind = el.get("type")
        if kind not in ("way", "relation"):
            continue
        ref = f"{kind}/{el['id']}"
        if kind == "way":
            geom, problem = _way_polygon(el)
        else:
            geom, problem = _relation_polygon(el)
        out.features.append(OsmFeature(ref=ref, tags=el.get("tags", {}), geom=geom, problem=problem))
    return out
