from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import shapely
import shapely.ops
import shapely.wkt
from hyp3lib.util import GDALConfigManager
from osgeo import gdal, osr
from shapely.geometry import LinearRing, Polygon, box


gdal.UseExceptions()

EARTH_APPROX_CIRCUMFERENCE = 40075017.0
EARTH_RADIUS = EARTH_APPROX_CIRCUMFERENCE / (2 * np.pi)


def margin_km_to_deg(margin_in_km: float) -> float:
    """Converts a margin value from kilometers to degrees."""
    km_to_deg_at_equator = 1000.0 / (EARTH_APPROX_CIRCUMFERENCE / 360.0)
    margin_in_deg = margin_in_km * km_to_deg_at_equator
    return margin_in_deg


def margin_km_to_longitude_deg(margin_in_km: float, lat: float) -> float:
    """Converts a margin value from kilometers to degrees as a function of latitude."""
    delta_lon = 180 * 1000 * margin_in_km / (np.pi * EARTH_RADIUS * np.cos(np.pi * lat / 180))
    return delta_lon


def polygon_from_bounds(bounds: tuple[float, float, float, float]) -> Polygon:
    """Create a polygon (EPSG:4326) from the lat/lon coordinates corresponding to a provided bounding box."""
    lon_min, lat_min, lon_max, lat_max = bounds
    # note we can also use the center lat here
    lat_worst_case = max([lat_min, lat_max])
    margin_in_km = 50.0
    lat_margin = margin_km_to_deg(margin_in_km)
    lon_margin = margin_km_to_longitude_deg(margin_in_km, lat=lat_worst_case)
    # Check if the bbox crosses the antimeridian and apply the margin accordingly
    # so that any resultant DEM is split properly by check_dateline
    if lon_max - lon_min > 180:
        lon_min, lon_max = lon_max, lon_min

    poly = box(
        lon_min - lon_margin, max([lat_min - lat_margin, -90]), lon_max + lon_margin, min([lat_max + lat_margin, 90])
    )
    return poly


def split_antimeridian(poly: Polygon) -> list[Polygon]:
    """Check if the provided polygon crosses the antimeridian and split it if it does."""
    x_min, _, x_max, _ = poly.bounds

    # Check anitmeridian crossing
    if (x_max - x_min > 180.0) or (x_min <= 180.0 <= x_max):
        dateline = shapely.wkt.loads('LINESTRING( 180.0 -90.0, 180.0 90.0)')

        # build new polygon with all longitudes between 0 and 360
        x, y = poly.exterior.coords.xy
        new_x = (k + (k <= 0.0) * 360 for k in x)
        new_ring = LinearRing(zip(new_x, y))

        # Split input polygon
        # (https://gis.stackexchange.com/questions/232771/splitting-polygon-by-linestring-in-geodjango_)
        # FIXME: mypy flags the following line because `dateline` is the wrong type, confirm that this works
        merged_lines = shapely.ops.linemerge([dateline, new_ring])  # type: ignore[list-item]
        border_lines = shapely.ops.unary_union(merged_lines)
        decomp = shapely.ops.polygonize(border_lines)

        polys = list(decomp)

        for polygon_count in range(len(polys)):
            x, y = polys[polygon_count].exterior.coords.xy
            # if there are no longitude values above 180, continue
            if not any([k > 180 for k in x]):
                continue

            # otherwise, wrap longitude values down by 360 degrees
            x_wrapped_minus_360 = np.asarray(x) - 360
            polys[polygon_count] = Polygon(zip(x_wrapped_minus_360, y))

    else:
        # If dateline is not crossed, treat input poly as list
        polys = [poly]

    return polys


def snap_coord(val: float, snap: float, offset: float, round_func: Callable) -> float:
    return round_func(float(val - offset) / snap) * snap + offset


def translate_dem(vrt_filename: str, output_path: str, bounds: tuple[float, float, float, float]) -> None:
    """Write a local subset of the OPERA DEM for a region matching the provided bounds.

    Params:
        vrt_filename: Path to the input VRT file
        output_path: Path to the translated output GTiff file
        bounds: Bounding box in the form of (lon_min, lat_min, lon_max, lat_max)
    """
    ds = gdal.Open(vrt_filename, gdal.GA_ReadOnly)

    # update cropping coordinates to not exceed the input DEM bounding box
    input_x_min, xres, _, input_y_max, _, yres = ds.GetGeoTransform()
    length = ds.GetRasterBand(1).YSize
    width = ds.GetRasterBand(1).XSize

    # Snap edge coordinates using the DEM pixel spacing
    # (xres and yres) and starting coordinates (input_x_min and
    # input_x_max). Maximum values are rounded using np.ceil
    # and minimum values are rounded using np.floor
    x_min, y_min, x_max, y_max = bounds
    snapped_x_min = snap_coord(x_min, xres, input_x_min, np.floor)
    snapped_x_max = snap_coord(x_max, xres, input_x_min, np.ceil)
    snapped_y_min = snap_coord(y_min, yres, input_y_max, np.floor)
    snapped_y_max = snap_coord(y_max, yres, input_y_max, np.ceil)

    input_y_min = input_y_max + length * yres
    input_x_max = input_x_min + width * xres

    adjusted_x_min = max(snapped_x_min, input_x_min)
    adjusted_x_max = min(snapped_x_max, input_x_max)
    adjusted_y_min = max(snapped_y_min, input_y_min)
    adjusted_y_max = min(snapped_y_max, input_y_max)

    try:
        gdal.Translate(
            output_path, ds, format='GTiff', projWin=[adjusted_x_min, adjusted_y_max, adjusted_x_max, adjusted_y_min]
        )
    except RuntimeError as err:
        if 'negative width and/or height' in str(err):
            gdal.Translate(output_path, ds, format='GTiff', projWin=[x_min, y_max, x_max, y_min])
        else:
            raise

    # stage_dem.py takes a bbox as an input. The longitude coordinates
    # of this bbox are unwrapped i.e., range in [0, 360] deg. If the
    # bbox crosses the anti-meridian, the script divides it in two
    # bboxes neighboring the anti-meridian. Here, x_min and x_max
    # represent the min and max longitude coordinates of one of these
    # bboxes. We Add 360 deg if the min longitude of the downloaded DEM
    # tile is < 180 deg i.e., there is a dateline crossing.
    # This ensures that the mosaicked DEM VRT will span a min
    # range of longitudes rather than the full [-180, 180] deg
    sr = osr.SpatialReference(ds.GetProjection())
    epsg_str = sr.GetAttrValue('AUTHORITY', 1)

    if x_min <= -180.0 and epsg_str == '4326':
        ds = gdal.Open(output_path, gdal.GA_Update)
        geotransform = list(ds.GetGeoTransform())
        geotransform[0] += 360.0
        ds.SetGeoTransform(tuple(geotransform))


def download_opera_dem_for_footprint(outfile: Path, bounds: tuple[float, float, float, float]) -> None:
    """Download a DEM from the specified S3 bucket.

    Params:
        outfile: Path to the where the output DEM file is to be staged.
        bounds: Bounding box in the form of (lon_min, lat_min, lon_max, lat_max).
    """
    poly = polygon_from_bounds(bounds)
    polys = split_antimeridian(poly)
    dem_list = []

    with NamedTemporaryFile(suffix='.txt') as cookie_file:
        with GDALConfigManager(
            GDAL_HTTP_COOKIEJAR=cookie_file.name,
            GDAL_HTTP_COOKIEFILE=cookie_file.name,
            GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',
        ):
            vrt_filename = '/vsicurl/https://nisar.asf.earthdatacloud.nasa.gov/STATIC/DEM/v1.1/EPSG4326/EPSG4326.vrt'
            for idx, poly in enumerate(polys):
                output_path = f'{outfile.stem}_{idx}.tif'
                dem_list.append(output_path)
                translate_dem(vrt_filename, output_path, bounds)

            gdal.BuildVRT(str(outfile), dem_list)
