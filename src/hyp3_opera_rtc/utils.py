import logging
import netrc
import os
from pathlib import Path
from platform import system
from typing import Tuple

import numpy as np
import rasterio
import requests
import shapely
from dem_stitcher import stitch_dem
from hyp3lib.get_orb import downloadSentinelOrbitFile
from osgeo import gdal
from shapely.geometry import LinearRing, Polygon


gdal.UseExceptions()
log = logging.getLogger(__name__)
ESA_HOST = 'dataspace.copernicus.eu'
EARTHDATA_HOST = 'urs.earthdata.nasa.gov'
DEM_URL = 'https://nisar.asf.earthdatacloud.nasa.gov/STATIC/DEM/v1.1'


def get_netrc() -> Path:
    """Get the location of the netrc file.

    Returns:
        Path to the netrc file
    """
    netrc_name = '_netrc' if system().lower() == 'windows' else '.netrc'
    netrc_file = Path.home() / netrc_name
    return netrc_file


def set_creds(service, username, password) -> None:
    """Set username/password environmental variables for a service.
    username/password are set using the following format:
    SERVICE_USERNAME, SERVICE_PASSWORD

    Args:
        service: Service to set credentials for
        username: Username for the service
        password: Password for the service
    """
    if username is not None:
        os.environ[f'{service.upper()}_USERNAME'] = username

    if password is not None:
        os.environ[f'{service.upper()}_PASSWORD'] = password


def find_creds_in_env(username_name, password_name) -> Tuple[str, str]:
    """Find credentials for a service in the environment.

    Args:
        username_name: Name of the environment variable for the username
        password_name: Name of the environment variable for the password

    Returns:
        Tuple of the username and password found in the environment
    """
    if username_name in os.environ and password_name in os.environ:
        username = os.environ[username_name]
        password = os.environ[password_name]
        return username, password

    return None, None


def find_creds_in_netrc(service) -> Tuple[str, str]:
    """Find credentials for a service in the netrc file.

    Args:
        service: Service to find credentials for

    Returns:
        Tuple of the username and password found in the netrc file
    """
    netrc_file = get_netrc()
    if netrc_file.exists():
        netrc_credentials = netrc.netrc(netrc_file)
        if service in netrc_credentials.hosts:
            username = netrc_credentials.hosts[service][0]
            password = netrc_credentials.hosts[service][2]
            return username, password

    return None, None


def get_esa_credentials() -> Tuple[str, str]:
    """Get ESA credentials from the environment or netrc file.

    Returns:
        Tuple of the ESA username and password
    """
    username, password = find_creds_in_env('ESA_USERNAME', 'ESA_PASSWORD')
    if username and password:
        return username, password

    username, password = find_creds_in_netrc(ESA_HOST)
    if username and password:
        return username, password

    raise ValueError(
        'Please provide Copernicus Data Space Ecosystem (CDSE) credentials via the '
        'ESA_USERNAME and ESA_PASSWORD environment variables, or your netrc file.'
    )


def get_earthdata_credentials() -> Tuple[str, str]:
    """Get NASA EarthData credentials from the environment or netrc file.

    Returns:
        Tuple of the NASA EarthData username and password
    """
    username, password = find_creds_in_env('EARTHDATA_USERNAME', 'EARTHDATA_PASSWORD')
    if username and password:
        return username, password

    username, password = find_creds_in_netrc(EARTHDATA_HOST)
    if username and password:
        return username, password

    raise ValueError(
        'Please provide NASA EarthData credentials via the '
        'EARTHDATA_USERNAME and EARTHDATA_PASSWORD environment variables, or your netrc file.'
    )


def download_orbit(granule_name: str, output_dir: Path) -> Path:
    """Download a S1 orbit file. Prefer using the ESA API,
    but fallback to ASF if needed.

    Args:
        granule_name: Name of the granule to download
        output_dir: Directory to save the orbit file in

    Returns:
        Path to the downloaded orbit file
    """
    orbit_path, _ = downloadSentinelOrbitFile(granule_name, str(output_dir), esa_credentials=get_esa_credentials())
    return orbit_path


def download_dem_for_footprint(dem_path: Path, footprint: Polygon) -> Path:
    """Download a DEM for the given footprint.
    Args:
        dem_path: The path to download the DEM to.
        footprint: The footprint to download a DEM for.

    Returns:
        Path to the downloaded DEM
    """
    if not dem_path.exists():
        X, p = stitch_dem(footprint.bounds, dem_name='glo_30', dst_ellipsoidal_height=False, dst_area_or_point='Point')
        with rasterio.open(dem_path, 'w', **p) as ds:
            ds.write(X, 1)
            ds.update_tags(AREA_OR_POINT='Point')
    return dem_path


def download_burst_db(save_dir: Path) -> Path:
    """Download the OPERA burst database.
    Currently using a version created using opera-adt/burst_db v0.4.0, but hope to switch to ASF-provide source.

    Args:
        save_dir: Directory to save the database to

    Returns:
        Path to the downloaded database
    """
    db_path = save_dir / 'opera-burst-bbox-only.sqlite3'
    url = 'https://ffwilliams2-shenanigans.s3.us-west-2.amazonaws.com/opera/opera-burst-bbox-only.sqlite3'

    if not db_path.exists():
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(db_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    return db_path


def check_dateline(poly):
    """
    Split `poly` if it crosses the dateline.

    Parameters
    ----------
    poly : shapely.geometry.Polygon
        Input polygon.

    Returns
    -------
    polys : list of shapely.geometry.Polygon
        A list containing: the input polygon if it didn't cross the dateline, or
        two polygons otherwise (one on either side of the dateline).

    """
    x_min, _, x_max, _ = poly.bounds

    # Check dateline crossing
    if (x_max - x_min > 180.0) or (x_min <= 180.0 <= x_max):
        dateline = shapely.wkt.loads('LINESTRING( 180.0 -90.0, 180.0 90.0)')

        # build new polygon with all longitudes between 0 and 360
        x, y = poly.exterior.coords.xy
        new_x = (k + (k <= 0.0) * 360 for k in x)
        new_ring = LinearRing(zip(new_x, y))

        # Split input polygon
        # (https://gis.stackexchange.com/questions/232771/splitting-polygon-by-linestring-in-geodjango_)
        merged_lines = shapely.ops.linemerge([dateline, new_ring])
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


def snap_coord(val, snap, offset, round_func):
    """Snap edge coordinates using the DEM"""
    return round_func(float(val - offset) / snap) * snap + offset


def translate_dem(vrt_filename, output_path, footprint):
    """
    Translate a DEM from S3 to a region matching the provided boundaries.

    Notes
    -----
    This function is decorated to perform retries using exponential backoff to
    make the remote call resilient to transient issues stemming from network
    access, authorization and AWS throttling (see "Query throttling" section at
    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html).

    Parameters
    ----------
    vrt_filename: str
        Path to the input VRT file
    output_path: str
        Path to the translated output GTiff file
    x_min: float
        Minimum longitude bound of the sub-window
    x_max: float
        Maximum longitude bound of the sub-window
    y_min: float
        Minimum latitude bound of the sub-window
    y_max: float
        Maximum latitude bound of the sub-window

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
    x_min, y_min, x_max, y_max = footprint.bounds
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
            print(
                'Adjusted window translation failed due to negative width and/or height, '
                'defaulting to original projection window'
            )
            gdal.Translate(output_path, ds, format='GTiff', projWin=[x_min, y_max, x_max, y_min])
            return

        raise


def download_opera_dem_for_footprint(outfile: Path, footprint: Polygon):
    """
    Download the OPERA/NISAR DEM from ASF.

    Parameters:
    ----------
    polys: list of shapely.geometry.Polygon
        List of shapely polygons.
    dem_location : str
       S3 bucket and key containing the global DEM to download from.
    outfile:
        Path to the where the output DEM file is to be staged.

    """
    footprints = check_dateline(footprint)
    dem_list = []
    for idx, footprint in enumerate(footprints):
        vrt_filename = f'/vsicurl/{DEM_URL}/EPSG4326/EPSG4326.vrt'
        output_path = outfile.parent / f'dem_{idx}.tif'
        dem_list.append(output_path)
        translate_dem(vrt_filename, output_path, footprint.bounds)

    gdal.BuildVRT(str(outfile), dem_list)
