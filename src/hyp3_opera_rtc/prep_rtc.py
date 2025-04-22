import argparse
import os
import warnings
from pathlib import Path

from hyp3lib.fetch import write_credentials_to_netrc_file
from jinja2 import Template

from hyp3_opera_rtc.prep_burst import prep_burst


def render_runconfig(
    config_path: Path,
    granule_name: str,
    orbit_name: str,
    db_name: str,
    dem_name: str,
    resolution: int = 30,
    container_base_path: Path = Path('/home/rtc_user/scratch'),
) -> None:
    input_dir = container_base_path / 'input'
    scratch_dir = container_base_path / 'scratch'
    output_dir = container_base_path / 'output'

    granule_path = input_dir / granule_name
    orbit_path = input_dir / orbit_name
    db_path = input_dir / db_name
    dem_path = input_dir / dem_name

    runconfig_dict = {
        'granule_path': str(granule_path),
        'orbit_path': str(orbit_path),
        'db_path': str(db_path),
        'dem_path': str(dem_path),
        'scratch_dir': str(scratch_dir),
        'output_dir': str(output_dir),
        'resolution': int(resolution),
    }

    template_dir = Path(__file__).parent / 'templates'
    with (template_dir / 'pge.yml').open() as file:
        template = Template(file.read())
        template_str = template.render(runconfig_dict)

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

    granule_path, orbit_path, db_path, dem_path = prep_burst(co_pol_granule, work_dir=input_dir)

    config_path = work_dir / 'runconfig.yml'
    render_runconfig(
        config_path=config_path,
        granule_name=granule_path.name,
        orbit_name=orbit_path.name,
        db_name=db_path.name,
        dem_name=dem_path.name,
        resolution=resolution,
    )


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
        write_credentials_to_netrc_file(username, password, append=False)

    if not (Path.home() / '.netrc').exists():
        warnings.warn(
            'Earthdata credentials must be present as environment variables, or in your netrc.',
            UserWarning,
        )

    prep_rtc(args.co_pol_granule, args.work_dir, args.resolution)


if __name__ == '__main__':
    main()
