import argparse
import os
import warnings
from pathlib import Path
from shutil import make_archive
from zipfile import ZipFile

import hyp3lib.fetch
import lxml.etree as ET
import requests
from burst2safe.burst2safe import burst2safe
from jinja2 import Template
from shapely.geometry import Polygon, box

from hyp3_opera_rtc import dem, orbit


CMR_URL = 'https://cmr.earthdata.nasa.gov/search/granules.umm_json'


def download_burst_db(save_dir: Path) -> Path:
    db_path = save_dir / 'opera-burst-bbox-only.sqlite3'

    if db_path.exists():
        return db_path

    # Currently using a version created using opera-adt/burst_db v0.4.0, but hope to switch to ASF-provide source.
    url = 'https://ffwilliams2-shenanigans.s3.us-west-2.amazonaws.com/opera/opera-burst-bbox-only.sqlite3'
    db_path = hyp3lib.fetch.download_file(url, str(save_dir))
    return Path(db_path)


def get_s1_granule_bbox(granule_path: Path, buffer: float = 0.025) -> Polygon:
    if granule_path.suffix == '.zip':
        with ZipFile(granule_path, 'r') as z:
            manifest_path = [x for x in z.namelist() if x.endswith('manifest.safe')][0]
            with z.open(manifest_path) as m:
                manifest = ET.parse(m).getroot()
    else:
        manifest_path = str(granule_path / 'manifest.safe')
        manifest = ET.parse(manifest_path).getroot()

    frame_element = next(x for x in manifest.findall('.//metadataObject') if x.get('ID') == 'measurementFrameSet')
    coords_element = frame_element.find('.//{http://www.opengis.net/gml}coordinates')
    assert coords_element is not None

    frame_string = coords_element.text
    assert frame_string is not None

    coord_strings = [pair.split(',') for pair in frame_string.split(' ')]
    coords = [(float(lon), float(lat)) for lat, lon in coord_strings]
    footprint = Polygon(coords).buffer(buffer)
    return box(*footprint.bounds)


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


def render_template(params: dict, work_dir: Path) -> None:
    template_dir = Path(__file__).parent / 'templates'
    with (template_dir / 'pge.yml.j2').open() as file:
        template = Template(file.read())
        template_str = template.render(params)

    config_path = work_dir / 'runconfig.yml'
    with config_path.open('w') as file:
        file.write(template_str)


def prep_rtc(
    co_pol_granule: str,
    work_dir: Path,
    resolution: int = 30,
) -> None:
    """Prepare data for OPERA RTC processing.

    Args:
        co_pol_granule: Sentinel-1 level-1 co-pol burst granule
        resolution: Resolution of the output RTC (m)
        work_dir: Working directory for processing
    """
    scratch_dir = work_dir / 'scratch'
    input_dir = work_dir / 'input'
    output_dir = work_dir / 'output'
    for d in [scratch_dir, input_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    validate_co_pol_granule(co_pol_granule)

    cross_pol_granule = get_cross_pol_name(co_pol_granule)
    dual_pol = granule_exists(cross_pol_granule)
    if dual_pol:
        print(f'Found cross-pol granule: {cross_pol_granule}')
        granules = [co_pol_granule, cross_pol_granule]
    else:
        print('No cross-pol granule found')
        granules = [co_pol_granule]

    safe_path = burst2safe(granules=granules, all_anns=True, work_dir=input_dir)
    granule_path = Path(make_archive(base_name=str(safe_path.with_suffix('')), format='zip', base_dir=str(safe_path)))
    print(f'Created archive: {granule_path}')

    orbit_path = orbit.get_orbit(safe_path.with_suffix('').name, save_dir=input_dir)
    print(f'Downloaded orbit file: {orbit_path}')

    db_path = download_burst_db(input_dir)
    print(f'Downloaded burst database: {db_path}')

    dem_path = input_dir / 'dem.tif'
    granule_bbox = get_s1_granule_bbox(granule_path)
    dem.download_opera_dem_for_footprint(dem_path, granule_bbox)
    print(f'Downloaded DEM: {dem_path}')

    runconfig_dict = {
        'granule_path': str(granule_path),
        'orbit_path': str(orbit_path),
        'db_path': str(db_path),
        'dem_path': str(dem_path),
        'scratch_dir': str(scratch_dir),
        'output_dir': str(output_dir),
        'dual_pol': dual_pol,
        'resolution': int(resolution),
    }

    render_template(runconfig_dict, work_dir)


def main() -> None:
    """Prepare for OPERA RTC processing.

    Example commands:
    python -m hyp3_opera_rtc.prep_rtc \
        S1_245714_IW1_20240809T141633_VV_6B31-BURST
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('co_pol_granule', help='Sentinel-1 co-pol burst granule')
    parser.add_argument('--work-dir', type=Path, required=True, help='Working directory for processing')
    parser.add_argument('--resolution', default=30, type=int, help='Resolution of the output RTC (m)')

    args, _ = parser.parse_known_args()

    username = os.getenv('EARTHDATA_USERNAME')
    password = os.getenv('EARTHDATA_PASSWORD')
    if username and password:
        hyp3lib.fetch.write_credentials_to_netrc_file(username, password, append=False)

    if not (Path.home() / '.netrc').exists():
        warnings.warn(
            'Earthdata credentials must be present as environment variables, or in your netrc.',
            UserWarning,
        )

    prep_rtc(args.co_pol_granule, args.work_dir, args.resolution)


if __name__ == '__main__':
    main()
