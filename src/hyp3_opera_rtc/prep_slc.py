import argparse
from pathlib import Path
from typing import Optional

from hyp3_opera_rtc import dem, orbit, utils


def prep_slc(
    granule: str,
    use_resorb: bool = True,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-0 granules to back-project
        use_resorb: Use the RESORB orbits instead of the POEORB orbits
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    print('Downloading data...')
    granule_path = work_dir / f'{granule}.zip'
    utils.download_s1_granule(granule, work_dir)

    orbit_type = 'AUX_RESORB' if use_resorb else 'AUX_POEORB'
    orbit_path = orbit.download_sentinel_orbit_file(granule, work_dir, orbit_types=[orbit_type])

    db_path = utils.download_burst_db(work_dir)

    granule_bbox = utils.get_s1_granule_bbox(granule_path)
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
