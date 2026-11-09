"""Boundary validation and area calculation for green-space polygons."""

from dataclasses import dataclass

from pyproj import Geod
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.validation import explain_validity

from app.config import get_settings

_GEOD = Geod(ellps="WGS84")


class GeometryError(ValueError):
    """A boundary failed validation; the message is suitable for display."""


@dataclass
class ValidBoundary:
    geom: MultiPolygon
    area_m2: float

    @property
    def wkt(self) -> str:
        return self.geom.wkt

    def geojson(self) -> dict:
        return mapping(self.geom)


def geodesic_area_m2(geom: Polygon | MultiPolygon) -> float:
    return abs(_GEOD.geometry_area_perimeter(geom)[0])


def pilot_area() -> Polygon:
    return box(*get_settings().pilot_bbox)


def as_multipolygon(geom) -> MultiPolygon:
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    raise GeometryError("The boundary must be a polygon.")


def validate_boundary(geojson: dict) -> ValidBoundary:
    """Validate a GeoJSON Polygon/MultiPolygon drawn by a user.

    Rules (AC-05.2): every ring has at least three distinct vertices, the shape does not
    intersect itself, it has a positive area, and it lies entirely inside the pilot area.
    """
    try:
        geom = shape(geojson)
    except Exception as exc:  # malformed coordinates
        raise GeometryError("The boundary coordinates could not be read.") from exc

    polygons = [geom] if isinstance(geom, Polygon) else list(getattr(geom, "geoms", []))
    if not polygons:
        raise GeometryError("The boundary must be a polygon.")
    for poly in polygons:
        if not isinstance(poly, Polygon):
            raise GeometryError("The boundary must be a polygon.")
        distinct = set(poly.exterior.coords)
        if len(distinct) < 3:
            raise GeometryError("A boundary needs at least three distinct points.")

    if not geom.is_valid:
        reason = explain_validity(geom)
        if "Self-intersection" in reason or "Ring Self-intersection" in reason:
            raise GeometryError("The boundary crosses itself. Redraw it so the edges do not intersect.")
        raise GeometryError(f"The boundary is not a valid polygon ({reason}).")

    if geom.area <= 0:
        raise GeometryError("The boundary has no area.")

    if not pilot_area().contains(geom):
        raise GeometryError("The boundary must lie entirely inside the Riyadh pilot area.")

    mp = as_multipolygon(geom)
    return ValidBoundary(geom=mp, area_m2=geodesic_area_m2(mp))
