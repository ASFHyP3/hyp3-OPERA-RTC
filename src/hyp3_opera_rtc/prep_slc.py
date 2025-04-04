import argparse
from pathlib import Path
from typing import Optional

from hyp3_opera_rtc import dem, utils
from hyp3_opera_rtc.orbit import get_orbit


def prep_slc(
    granule: str,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granule: Sentinel-1 SLC granule to create RTC datasets for
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    print('Downloading data...')

    granule_path = work_dir / f'{granule}.zip'
    if not granule_path.exists():
        utils.download_s1_granule(granule, work_dir)

    if len(list(work_dir.glob('*.EOF'))) == 0:
        orbit_path = get_orbit(granule, save_dir=work_dir)
    else:
        orbit_path = work_dir / list(work_dir.glob('*.EOF'))[0].name

    db_path = utils.download_burst_db(work_dir)

    dem_path = work_dir / 'dem.tif'
    granule_bbox = utils.get_s1_granule_bbox(granule_path)
    dem.download_opera_dem_for_footprint(dem_path, granule_bbox)
    return granule_path, orbit_path, db_path, dem_path


def main() -> None:
    """Prep SLC entrypoint.

    Example command:
    python -m hyp3_opera_rtc ++process prep_slc S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granule', help='S1 granule to load data for.')
    parser.add_argument('--work-dir', default=None, help='Working directory for processing')

    args = parser.parse_args()

    prep_slc(**args.__dict__)


if __name__ == '__main__':
    main()
