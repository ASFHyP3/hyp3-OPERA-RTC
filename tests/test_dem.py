from shapely.geometry import Polygon, box

from hyp3_opera_rtc import dem


def test_margin_km_to_deg():
    assert round(dem.margin_km_to_deg(1), 3) == 0.009
    assert round(dem.margin_km_to_deg(0), 3) == 0.000
    assert round(dem.margin_km_to_deg(-1), 3) == -0.009


def test_margin_km_to_longitude_deg():
    assert round(dem.margin_km_to_longitude_deg(1, 0), 3) == 0.009
    assert round(dem.margin_km_to_longitude_deg(1, 45), 3) == 0.013
    assert round(dem.margin_km_to_longitude_deg(1, -45), 3) == 0.013
    assert round(dem.margin_km_to_longitude_deg(0, 0), 3) == 0.000
    assert round(dem.margin_km_to_longitude_deg(-1, 0), 3) == -0.009


def test_polygon_from_bounds():
    poly = dem.polygon_from_bounds((-1, -1, 0, 0))
    assert isinstance(poly, Polygon)
    assert tuple([round(x, 2) for x in poly.bounds]) == (-1.45, -1.45, 0.45, 0.45)

    cross_poly = dem.polygon_from_bounds((180, -1, 181, 0))
    assert isinstance(cross_poly, Polygon)
    assert tuple([round(x, 2) for x in cross_poly.bounds]) == (179.55, -1.45, 181.45, 0.45)


def test_check_antimeridean():
    no_cross = box(-1, -1, 0, 0)
    polys = dem.check_antimeridean(no_cross)
    assert len(polys) == 1
    assert polys[0].equals(no_cross)

    cross = box(179, -1, 181, 0)
    polys = dem.check_antimeridean(cross)
    negative_side = box(-180, -1, -179, 0)
    positive_side = box(179, -1, 180, 0)
    assert len(polys) == 2
    assert polys[0].equals(negative_side)
    assert polys[1].equals(positive_side)
