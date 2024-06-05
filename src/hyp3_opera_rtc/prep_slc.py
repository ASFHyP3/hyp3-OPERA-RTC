import argparse
from pathlib import Path
from typing import Optional, Tuple
from zipfile import ZipFile

import asf_search
from shapely.geometry import Polygon, shape

from hyp3_opera_rtc import dem, utils


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
    use_reseorb: bool = True,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-0 granules to back-project
        use_reseorb: Use the RESORB orbits instead of the POEORB orbits
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    print('Downloading data...')
    granule_path, granule_bbox = download_slc_granule(granule, work_dir)
    orbit_type = 'AUX_RESORB' if use_reseorb else 'AUX_POEORB'
    orbit_path = utils.download_orbit(granule, work_dir, orbit_type=orbit_type)
    db_path = utils.download_burst_db(work_dir)
    dem_path = work_dir / 'dem.tif'
    dem.download_opera_dem_for_footprint(dem_path, granule_bbox.buffer(0.15))
    return granule_path, orbit_path, db_path, dem_path


def main():
    """Prep SLC entrypoint.

    Example command:
    python -m hyp3_opera_rtc ++process prep_slc S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granule', help='S1 granule to load data for.')
    parser.add_argument('--use-resorb', action='store_true', help='Use RESORB orbits instead of POEORB orbits')
    parser.add_argument('--work-dir', default=None, help='Working directory for processing')

    args = parser.parse_args()

    prep_slc(**args.__dict__)


if __name__ == '__main__':
    main()
