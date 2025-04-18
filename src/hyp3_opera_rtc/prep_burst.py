from pathlib import Path
from shutil import make_archive

from burst2safe.burst2safe import burst2safe

from hyp3_opera_rtc import dem, orbit, utils


def prep_burst(
    granules: list[str],
    work_dir: Path | None = None,
) -> tuple[Path, Path, Path, Path]:
    """Prepare data for burst-based processing.

    Args:
        granules: Sentinel-1 burst SLC granules to create RTC dataset for
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    print('Downloading data...')

    if len(list(work_dir.glob('S1*.zip'))) == 0:
        granule_path = burst2safe(granules=granules, all_anns=True, work_dir=work_dir)
        make_archive(base_name=str(granule_path.with_suffix('')), format='zip', base_dir=str(granule_path))
        granule = granule_path.with_suffix('').name
        granule_path = granule_path.with_suffix('.zip')
    else:
        granule_path = work_dir / list(work_dir.glob('S1*.zip'))[0].name

    if len(list(work_dir.glob('*.EOF'))) == 0:
        orbit_path = orbit.get_orbit(granule, save_dir=work_dir)
    else:
        orbit_path = work_dir / list(work_dir.glob('*.EOF'))[0].name

    db_path = utils.download_burst_db(work_dir)

    dem_path = work_dir / 'dem.tif'
    granule_bbox = utils.get_s1_granule_bbox(granule_path)
    dem.download_opera_dem_for_footprint(dem_path, granule_bbox)
    return granule_path, orbit_path, db_path, dem_path
