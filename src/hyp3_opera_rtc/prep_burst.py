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


def validate_co_pol_granule(granule: str) -> None:
    pol = granule.split('_')[4]
    if pol not in {'VV', 'HH'}:
        raise ValueError(f'{granule} has polarization {pol}, must be VV or HH')
    if not granule_exists(granule):
        raise ValueError(f'Granule does not exist: {granule}')


def get_cross_pol_name(granule: str) -> str:
    parts = granule.split('_')
    parts[4] = {'VV': 'VH', 'HH': 'HV'}[parts[4]]
    return '_'.join(parts)


def prep_burst(
    co_pol_granule: str,
    work_dir: Path | None = None,
) -> tuple[Path, Path, Path, Path, bool]:
    """Prepare data for burst-based processing.

    Args:
        co_pol_granule: Sentinel-1 level-1 co-pol burst granule
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    validate_co_pol_granule(co_pol_granule)

    cross_pol_granule = get_cross_pol_name(co_pol_granule)
    dual_pol = granule_exists(cross_pol_granule)
    if dual_pol:
        print(f'Found cross-pol granule: {cross_pol_granule}')
        granules = [co_pol_granule, cross_pol_granule]
    else:
        print('No cross-pol granule found')
        granules = [co_pol_granule]

    safe_path = burst2safe(granules=granules, all_anns=True, work_dir=work_dir)
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

    return zip_path, orbit_path, db_path, dem_path, dual_pol
