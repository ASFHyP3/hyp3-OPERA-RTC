import cgi
import logging
import netrc
import os
from os.path import basename
from pathlib import Path
from platform import system
from typing import Optional, Tuple, Union
from urllib.parse import urlparse
from zipfile import ZipFile

import lxml.etree as ET
import requests
from osgeo import gdal
from requests.adapters import HTTPAdapter
from shapely.geometry import Polygon, box
from urllib3.util.retry import Retry


gdal.UseExceptions()
log = logging.getLogger(__name__)
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


def _get_download_path(url: str, content_disposition: str = None, directory: Union[Path, str] = '.'):
    filename = None
    if content_disposition is not None:
        _, params = cgi.parse_header(content_disposition)
        filename = params.get('filename')
    if not filename:
        filename = basename(urlparse(url).path)
    if not filename:
        raise ValueError(f'could not determine download path for: {url}')
    return Path(directory) / filename


def download_file(
    url: str,
    directory: Union[Path, str] = '.',
    chunk_size=2**20,
    auth: Optional[Tuple[str, str]] = None,
    token: Optional[str] = None,
    retries=2,
    backoff_factor=1,
) -> str:
    """Download a file

    Args:
        url: URL of the file to download
        directory: Directory location to place files into
        chunk_size: Size to chunk the download into
        auth: Username and password for HTTP Basic Auth
        token: Token for HTTP Bearer authentication
        retries: Number of retries to attempt
        backoff_factor: Factor for calculating time between retries

    Returns:
        download_path: The path to the downloaded file
    """
    logging.info(f'Downloading {url}')

    session = requests.Session()
    session.auth = auth
    if token:
        session.headers.update({'Authorization': f'Bearer {token}'})

    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session.mount('https://', HTTPAdapter(max_retries=retry_strategy))
    session.mount('http://', HTTPAdapter(max_retries=retry_strategy))

    with session.get(url, stream=True) as s:
        download_path = _get_download_path(s.url, s.headers.get('content-disposition'), directory)
        s.raise_for_status()
        with open(download_path, 'wb') as f:
            for chunk in s.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
    session.close()

    return Path(download_path)


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
    download_file(url, save_dir)
    return db_path


def download_s1_granule(granule, save_dir: Path) -> Path:
    mission = granule[0] + granule[2]
    product_type = granule[7:10]
    if product_type == 'GRD':
        product_type += '_' + granule[10] + granule[14]
    url = f'https://sentinel1.asf.alaska.edu/{product_type}/{mission}/{granule}.zip'
    creds = get_earthdata_credentials()
    download_file(url, save_dir, auth=creds, chunk_size=10 * (2**20))
    return save_dir / f'{granule}.zip'


def get_s1_granule_bbox(granule_path: Path):
    if granule_path.suffix == '.zip':
        with ZipFile(granule_path, 'r') as z:
            manifest_path = [x for x in z.namelist() if x.endswith('manifest.safe')][0]
            with z.open(manifest_path) as m:
                manifest = ET.parse(m).getroot()
    else:
        manifest_path = granule_path / 'manifest.safe'
        manifest = ET.parse(manifest_path).getroot()

    frame_element = [x for x in manifest.findall('.//metadataObject') if x.get('ID') == 'measurementFrameSet'][0]
    frame_string = frame_element.find('.//{http://www.opengis.net/gml}coordinates').text
    coord_strings = [pair.split(',') for pair in frame_string.split(' ')]
    coords = [(float(lon), float(lat)) for lat, lon in coord_strings]
    footprint = Polygon(coords)
    return box(*footprint.bounds)
