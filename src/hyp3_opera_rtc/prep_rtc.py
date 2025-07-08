import argparse
import os
import shutil
import warnings
from pathlib import Path
from zipfile import ZipFile

import hyp3lib.fetch
import lxml.etree as ET
import requests
from hyp3lib.fetch import download_file
from hyp3lib.scene import get_download_url
from jinja2 import Template

from hyp3_opera_rtc import dem, orbit


CMR_URL = 'https://cmr.earthdata.nasa.gov/search/granules.umm_json'


def prep_burst_db(save_dir: Path) -> Path:
    db_filename = 'burst_db_0.2.0_230831-bbox-only.sqlite'
    db_path = save_dir / db_filename
    shutil.copy(Path.home() / db_filename, db_path)
    return db_path


def bounding_box_from_slc_granule(safe_file_path: Path) -> tuple[float, float, float, float]:
    """Extracts the bounding box footprint from the given SLC SAFE archive."""
    safe_file_name = safe_file_path.stem

    with ZipFile(safe_file_path) as myzip:
        with myzip.open(f'{safe_file_name}.SAFE/manifest.safe', 'r') as infile:
            manifest_tree = ET.parse(infile)

    coordinates_elem = manifest_tree.xpath('.//*[local-name()="coordinates"]')
    if coordinates_elem is None:
        raise RuntimeError(
            'Could not find gml:coordinates element within the manifest.safe '
            'of the provided SAFE archive, cannot determine DEM bounding box.'
        )

    assert isinstance(coordinates_elem, list)
    assert isinstance(coordinates_elem[0], ET._Element)
    coordinates_str = coordinates_elem[0].text
    assert isinstance(coordinates_str, str)
    coordinates = coordinates_str.split()
    lats = [float(coordinate.split(',')[0]) for coordinate in coordinates]
    lons = [float(coordinate.split(',')[-1]) for coordinate in coordinates]

    lat_min = min(lats)
    lat_max = max(lats)
    lon_min = min(lons)
    lon_max = max(lons)

    # Check if the bbox crosses the antimeridian and "unwrap" the coordinates
    # so that any resultant DEM is split properly by check_dateline
    if lon_max - lon_min > 180:
        lons = [lon + 360 if lon < 0 else lon for lon in lons]
        lon_min = min(lons)
        lon_max = max(lons)

    return (lon_min, lat_min, lon_max, lat_max)  # WSEN order


def get_slc_granule_cmr(granule: str) -> dict:
    params = (('short_name', 'SENTINEL-1*'), ('granule_ur', granule))  # TODO : Is this the correct wildcard?
    response = requests.get(CMR_URL, params=params)
    response.raise_for_status()
    return response.json()


def get_burst_granule_cmr(granule: str) -> dict:
    params = (('short_name', 'SENTINEL-1_BURSTS'), ('granule_ur', granule))
    response = requests.get(CMR_URL, params=params)
    response.raise_for_status()
    return response.json()


def granule_exists(granule: str, type: str = 'burst') -> bool:
    if type == 'burst':
        response = get_granule_cmr(granule)
    if type == 'slc':
        response = get_burst_granule_cmr(granule)
    return bool(response['items'])


def parse_response_for_params(response: dict) -> tuple[str, str]:
    assert len(response['items']) == 1
    item = response['items'][0]

    source_slc = item['umm']['InputGranules'][0][:-4]
    assert isinstance(source_slc, str)

    opera_burst_ids = [attr for attr in item['umm']['AdditionalAttributes'] if attr['Name'] == 'BURST_ID_FULL']
    assert len(opera_burst_ids) == 1
    opera_burst_id = opera_burst_ids[0]['Values'][0]
    assert isinstance(opera_burst_id, str)

    return source_slc, f't{opera_burst_id.lower()}'


def get_granule_burst_params(granule: str) -> tuple[str, str]:
    response = get_burst_granule_cmr(granule)
    return parse_response_for_params(response)


def get_granule_slc_params(granule: str) -> tuple[str, str]:
    response = get_slc_granule_cmr(granule)
    return parse_response_for_params(response)


def validate_slc_co_pol_granule(granule: str) -> bool:
    pol = granule.split('_')[4][2:4]
    if pol in {'VH', 'HV'}:
        raise ValueError(f'{granule} has polarization {pol}, must be VV or HH')
    if not granule_exists(granule, slc):
        raise ValueError(f'Granule does not exist: {granule}')


def validate_burst_co_pol_granule(granule: str) -> None:
    pol = granule.split('_')[4]
    if pol not in {'VV', 'HH'}:
        raise ValueError(f'{granule} has polarization {pol}, must be VV or HH')
    if not granule_exists(granule, burst):
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


def prep_burst_rtc(
    co_pol_granule: str,
    work_dir: Path,
    resolution: int = 30,
) -> None:
    """Prepare co_pol data for OPERA RTC processing.

    Args:
        co_pol_granule: Sentinel-1 level-1 co-pol granule (either burst or SLC)
        work_dir: Working directory for processing
        resolution: Resolution of the output RTC (m)
    """
    scratch_dir = work_dir / 'scratch_dir'
    input_dir = work_dir / 'input_dir'
    output_dir = work_dir / 'output_dir'
    for d in [scratch_dir, input_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if co_pol_granule.endswith('BURST'):
        validate_burst_co_pol_granule(co_pol_granule)
        source_slc, opera_burst_id = get_granule_slc_params(co_pol_granule)
    else:
        validate_slc_co_pol_granule(co_pol_granule)
        source_slc, opera_burst_id = get_granule_burst_params(co_pol_granule)

    safe_path = download_file(get_download_url(source_slc), directory=str(input_dir), chunk_size=10485760)
    safe_path = Path(safe_path)
    dual_pol = safe_path.name[14] == 'D'
    print(f'Created archive: {safe_path}')

    orbit_path = orbit.get_orbit(safe_path.with_suffix('').name, save_dir=input_dir)
    print(f'Downloaded orbit file: {orbit_path}')

    db_path = prep_burst_db(input_dir)
    print(f'Burst database: {db_path}')

    dem_path = input_dir / 'dem.tif'
    granule_bbox = bounding_box_from_slc_granule(safe_path)
    dem.download_opera_dem_for_footprint(dem_path, granule_bbox)
    print(f'Downloaded DEM: {dem_path}')

    runconfig_dict = {
        'granule_path': str(safe_path),
        'orbit_path': str(orbit_path),
        'db_path': str(db_path),
        'dem_path': str(dem_path),
        'opera_burst_id': opera_burst_id,
        'scratch_dir': str(scratch_dir),
        'output_dir': str(output_dir),
        'dual_pol': dual_pol,
        'resolution': int(resolution),
        'data_validity_start_date': '20140403',
    }

    render_template(runconfig_dict, work_dir)


def main() -> None:
    """Prepare for OPERA RTC processing.

    Example commands:
    python -m hyp3_opera_rtc.prep_rtc \
        S1_245714_IW1_20240809T141633_VV_6B31-BURST
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('co_pol_granule', help='Sentinel-1 co-pol burst granule or SLC')
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
