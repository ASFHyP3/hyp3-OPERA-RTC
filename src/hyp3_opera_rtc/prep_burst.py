import argparse
from pathlib import Path
from shutil import make_archive

import requests
from burst2safe.burst2safe import burst2safe

from hyp3_opera_rtc import dem, orbit, utils


def validate_co_pol_granules(granules: list[str]) -> None:
    for granule in granules:
        pol = granule.split('_')[4]
        if pol not in {'VV', 'HH'}:
            raise ValueError(f'{granule} has polarization {pol}, must be VV or HH')


def get_cross_pol_granule_name(granule: str) -> str:
    parts = granule.split('_')
    parts[4] = {'VV': 'VH', 'HH': 'HV'}[parts[4]]
    return '_'.join(parts)


def granule_exists(granule: str) -> bool:
    url = 'https://cmr.earthdata.nasa.gov/search/granules.umm_json'
    params = (('short_name', 'SENTINEL-1_BURSTS'), ('granule_ur', granule))
    response = requests.get(url, params=params)
    response.raise_for_status()
    return bool(response.json()['items'])


def get_cross_pol_granules(granules: list[str]) -> list[str]:
    cross_pol_granules = []
    for granule in granules:
        # TODO: should we assume that the co-pol granule exists, or confirm that it does?
        #  it should fail at burst2safe if doesn't exist, right?
        cross_pol_granule = get_cross_pol_granule_name(granule)
        if not granule_exists(cross_pol_granule):
            raise ValueError(f'Cross-pol granule {cross_pol_granule} for co-pol granule {granule} does not exist')
        cross_pol_granules.append(cross_pol_granule)
    return cross_pol_granules


def prep_burst(
    granules: list[str],
    work_dir: Path | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Prepare data for burst-based processing.

    Args:
        granules: Sentinel-1 burst SLC co-pol granules to create RTC dataset for
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    validate_co_pol_granules(granules)

    print('Downloading data...')

    # TODO: do we still want to allow for caching the zip file?
    if len(list(work_dir.glob('S1*.zip'))) == 0:
        cross_pol_granules = get_cross_pol_granules(granules)
        # TODO: add cross-pol granules to list passed to burst2safe; does order matter?
        granule_path = burst2safe(granules=granules, all_anns=True, work_dir=work_dir)
        make_archive(base_name=str(granule_path.with_suffix('')), format='zip', base_dir=str(granule_path))
        granule = granule_path.with_suffix('').name
        granule_path = granule_path.with_suffix('.zip')
    else:
        granule_path = work_dir / list(work_dir.glob('S1*.zip'))[0].name

    # TODO: do we still want to allow for caching the EOF file?
    if len(list(work_dir.glob('*.EOF'))) == 0:
        orbit_path = orbit.get_orbit(granule, save_dir=work_dir)
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
    python -m hyp3_opera_rtc ++process prep_burst \
        S1_136231_IW2_20200604T022312_VV_7C85-BURST S1_136231_IW2_20200604T022312_VH_7C85-BURST
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granules', nargs='+', help='S1 burst granules to load data for.')
    parser.add_argument('--work-dir', default=None, help='Working directory for processing')

    args = parser.parse_args()

    prep_burst(**args.__dict__)


if __name__ == '__main__':
    main()
