"""Boundary validation and area (AC-05.1, AC-05.2): unit tests without the database."""

import pytest
from shapely.geometry import box

from app.services.geometry import GeometryError, geodesic_area_m2, validate_boundary
from tests.conftest import square


def test_valid_square_area_is_geodesic():
    b = validate_boundary(square(46.70, 24.70, 0.001))
    # 0.001 deg lat ~ 110.8 m; 0.001 deg lon at 24.7 N ~ 101.2 m  -> ~11,200 m2
    assert 11_000 < b.area_m2 < 11_400
    assert b.geom.geom_type == "MultiPolygon"


def test_area_matches_independent_reference():
    # Independent check: spherical-Earth approximation of the same 0.01 x 0.01 degree cell.
    import math

    r = 6_371_008.8
    lat1, lat2 = math.radians(24.70), math.radians(24.71)
    approx = r * r * math.radians(0.01) * abs(math.sin(lat2) - math.sin(lat1))
    assert geodesic_area_m2(box(46.70, 24.70, 46.71, 24.71)) == pytest.approx(approx, rel=0.005)


@pytest.mark.parametrize(
    "geojson, message",
    [
        ({"type": "Polygon", "coordinates": [[[46.7, 24.7], [46.701, 24.7], [46.7, 24.7]]]}, "three distinct"),
        (  # bow-tie: edges cross
            {
                "type": "Polygon",
                "coordinates": [[[46.70, 24.70], [46.71, 24.71], [46.71, 24.70], [46.70, 24.71], [46.70, 24.70]]],
            },
            "crosses itself",
        ),
        (square(46.0, 24.0), "inside the Riyadh pilot area"),  # far outside
        (square(47.049, 24.80, 0.01), "inside the Riyadh pilot area"),  # straddles the edge
        ({"type": "Polygon", "coordinates": [[["a", "b"]]]}, "could not be read"),
    ],
)
def test_invalid_boundaries_rejected_with_message(geojson, message):
    with pytest.raises(GeometryError, match=message):
        validate_boundary(geojson)


def test_unclosed_ring_from_editor_is_closed_automatically():
    ring = square(46.70, 24.70)["coordinates"][0][:-1]
    assert validate_boundary({"type": "Polygon", "coordinates": [ring]}).area_m2 > 0
