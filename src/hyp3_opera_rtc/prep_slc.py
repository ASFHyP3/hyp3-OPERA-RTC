import argparse
from pathlib import Path
from typing import Optional, Tuple
from zipfile import ZipFile

import asf_search
from shapely.geometry import Polygon, shape

from hyp3_opera_rtc import utils


def download_slc_granule(granule_name: str, output_dir: Path, unzip: bool = False) -> Tuple[Path, Polygon]:
    """Download a S1 granule using asf_search. Return its path
    and buffered extent.

    Args:
        granule_name: Name of the granule to download
        output_dir: Directory to save the granule in

    Returns:
        Tuple of the granule path and its extent as a Polygon
    """
    username, password = utils.get_earthdata_credentials()
    session = asf_search.ASFSession().auth_with_creds(username, password)
    if not granule_name.endswith('-SLC'):
        granule_name += '-SLC'

    result = asf_search.granule_search([granule_name])[0]
    bbox = shape(result.geojson()['geometry'])

    if not unzip:
        out_path = output_dir / f'{granule_name[:-4]}.zip'
        result.download(path=output_dir, session=session)
    else:
        zip_path = output_dir / f'{granule_name[:-4]}.zip'
        out_path = output_dir / f'{granule_name[:-4]}.SAFE'

        if not out_path.exists() and not zip_path.exists():
            result.download(path=output_dir, session=session)

        if not out_path.exists():
            with ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall('.')

        if zip_path.exists():
            zip_path.unlink()

    return out_path, bbox


def prep_slc(
    granule: str,
    earthdata_username: str = None,
    earthdata_password: str = None,
    esa_username: str = None,
    esa_password: str = None,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-0 granules to back-project
        earthdata_username: Username for NASA's EarthData service
        earthdata_password: Password for NASA's EarthData service
        esa_username: Username for ESA's Copernicus Data Space Ecosystem
        esa_password: Password for ESA's Copernicus Data Space Ecosystem
        bucket: AWS S3 bucket for uploading the final product(s)
        bucket_prefix: Add a bucket prefix to the product(s)
        work_dir: Working directory for processing
    """
    utils.set_creds('EARTHDATA', earthdata_username, earthdata_password)
    utils.set_creds('ESA', esa_username, esa_password)
    if work_dir is None:
        work_dir = Path.cwd()

    print('Downloading data...')
    granule_path, granule_bbox = download_slc_granule(granule, work_dir)
    orbit_path = utils.download_orbit(granule, work_dir)
    dem_path = work_dir / 'dem.tif'
    utils.download_dem_for_footprint(granule_bbox, dem_path)
    return granule_path, orbit_path, dem_path


def main():
    """Prep SLC entrypoint.

    Example command:
    python -m hyp3_opera_rtc ++process prep_slc S1A_IW_SLC__1SDV_20221201T020814_20221201T020840_046132_0585C1_C7DE
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--earthdata-username', default=None, help="Username for NASA's EarthData")
    parser.add_argument('--earthdata-password', default=None, help="Password for NASA's EarthData")
    parser.add_argument('--esa-username', default=None, help="Username for ESA's Copernicus Data Space Ecosystem")
    parser.add_argument('--esa-password', default=None, help="Password for ESA's Copernicus Data Space Ecosystem")
    parser.add_argument('granule', help='S1 granule to load data for.')
    args = parser.parse_args()

    prep_slc(**args.__dict__)


if __name__ == '__main__':
    main()
