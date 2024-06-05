import logging
import netrc
import os
import urllib
from pathlib import Path
from platform import system
from typing import Optional, Tuple

import numpy as np
import rasterio
import requests
import shapely
from dem_stitcher import stitch_dem
from hyp3lib.get_orb import downloadSentinelOrbitFile
from osgeo import gdal
from requests.adapters import HTTPAdapter
from shapely.geometry import LinearRing, Polygon
from urllib3.util.retry import Retry

from hyp3_opera_rtc import utils


gdal.UseExceptions()
log = logging.getLogger(__name__)
ESA_HOST = 'dataspace.copernicus.eu'
EARTHDATA_HOST = 'urs.earthdata.nasa.gov'
DEM_URL = 'https://nisar.asf.earthdatacloud.nasa.gov/STATIC/DEM/v1.1'
AUTH_URL = (
    'https://urs.earthdata.nasa.gov/oauth/authorize?response_type=code&client_id=BO_n7nTIlMljdvU6kRRB3g'
    '&redirect_uri=https://auth.asf.alaska.edu/login&app_type=401'
)
PROFILE_URL = 'https://urs.earthdata.nasa.gov/profile'


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


def download_orbit(granule_name: str, output_dir: Path, orbit_type: Optional[str] = None) -> Path:
    """Download a S1 orbit file. Prefer using the ESA API,
    but fallback to ASF if needed.

    Args:
        granule_name: Name of the granule to download
        output_dir: Directory to save the orbit file in

    Returns:
        Path to the downloaded orbit file
    """
    if orbit_type is None:
        orbit_type = ('AUX_POEORB', 'AUX_RESORB')
    elif isinstance(orbit_type, str):
        orbit_type = tuple([orbit_type])

    orbit_path, _ = downloadSentinelOrbitFile(
        granule_name,
        str(output_dir),
        esa_credentials=get_esa_credentials(),
        orbit_types=orbit_type,
    )
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


class AuthenticationError(Exception):
    pass


def get_authenticated_session() -> requests.Session:
    """Log into EarthData using credentials for `urs.earthdata.nasa.gov` from either the provided
     credentials or a `.netrc` file.

    Returns:
        An authenticated HyP3 Session
    """
    s = requests.Session()
    auth = utils.get_earthdata_credentials()

    response = s.get(AUTH_URL, auth=auth)
    auth_error_message = (
        'Was not able to authenticate with credentials provided\n'
        'This could be due to invalid credentials or a connection error.'
    )

    parsed_url = urllib.parse.urlparse(response.url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    error_msg = query_params.get('error_msg')
    resolution_url = query_params.get('resolution_url')

    if error_msg is not None and resolution_url is not None:
        raise AuthenticationError(f'{error_msg[0]}: {resolution_url[0]}')

    if error_msg is not None and 'Please update your profile' in error_msg[0]:
        raise AuthenticationError(f'{error_msg[0]}: {PROFILE_URL}')

    try:
        response.raise_for_status()
    except requests.HTTPError:
        raise AuthenticationError(auth_error_message)

    return s


def download_earthdata_file(
    url: str, out_dir: Path, session: Optional[requests.Session] = None, retries=2, backoff_factor=1
) -> Path:
    """Download a file from EarthData using the provided URL.
    Args:
        url: URL of the file to download
        out_dir: Directory to save the downloaded file in
        retries: Number of retries to attempt
        backoff_factor: Factor for calculating time between retries
    Returns:
        download_path: The path to the downloaded file
    """
    filepath = out_dir / url.split('/')[-1]
    if session is None:
        session = get_authenticated_session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
    )

    session.mount('https://', HTTPAdapter(max_retries=retry_strategy))
    session.mount('http://', HTTPAdapter(max_retries=retry_strategy))
    with session.get(url, stream=True) as s:
        s.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in s.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    session.close()

    return filepath
