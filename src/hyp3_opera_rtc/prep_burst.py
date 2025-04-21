import argparse
from pathlib import Path
from shutil import make_archive

import requests
from burst2safe.burst2safe import burst2safe

from hyp3_opera_rtc import dem, orbit, utils


CMR_URL = 'https://cmr.earthdata.nasa.gov/search/granules.umm_json'


def granule_exists(granule: str) -> bool:
    params = (('short_name', 'SENTINEL-1_BURSTS'), ('granule_ur', granule))
    response = requests.get(CMR_URL, params=params)
    response.raise_for_status()
    return bool(response.json()['items'])


def get_cross_pol_name(granule: str) -> str:
    parts = granule.split('_')
    pol = parts[4]
    if pol not in {'VV', 'HH'}:
        raise ValueError(f'{granule} has polarization {pol}, must be VV or HH')
    parts[4] = {'VV': 'VH', 'HH': 'HV'}[pol]
    return '_'.join(parts)


def get_cross_pol_granules(granules: list[str]) -> list[str]:
    cross_pol_granules = [get_cross_pol_name(granule) for granule in granules]
    existing_cross_pol_granules = []
    for co_pol_granule, cross_pol_granule in zip(granules, cross_pol_granules):
        if not granule_exists(co_pol_granule):
            raise ValueError(f'Granule does not exist: {co_pol_granule}')
        if granule_exists(cross_pol_granule):
            existing_cross_pol_granules.append(cross_pol_granule)
    return existing_cross_pol_granules


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

    cross_pol_granules = get_cross_pol_granules(granules)
    print(f'Found {len(cross_pol_granules)} cross-pol granules: {cross_pol_granules}')

    safe_path = burst2safe(granules=granules + cross_pol_granules, all_anns=True, work_dir=work_dir)
    zip_path = Path(make_archive(base_name=str(safe_path.with_suffix('')), format='zip', base_dir=str(safe_path)))
    print(f'Created archive: {zip_path}')

    orbit_path = orbit.get_orbit(safe_path.with_suffix('').name, save_dir=work_dir)
    print(f'Downloaded orbit file: {orbit_path}')

    db_path = utils.download_burst_db(work_dir)
    print(f'Downloaded burst database: {db_path}')

    dem_path = work_dir / 'dem.tif'
    granule_bbox = utils.get_s1_granule_bbox(zip_path)
    dem.download_opera_dem_for_footprint(dem_path, granule_bbox)
    print(f'Downloaded DEM: {dem_path}')

    return zip_path, orbit_path, db_path, dem_path


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
