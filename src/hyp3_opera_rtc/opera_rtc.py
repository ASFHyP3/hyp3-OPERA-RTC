import argparse
import secrets
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from jinja2 import Template

from hyp3_opera_rtc.prep_burst import prep_burst
from hyp3_opera_rtc.prep_slc import prep_slc


def render_runconfig(
    config_path: Path,
    granule_name: str,
    orbit_name: str,
    db_name: str,
    dem_name: str,
    config_type: str = 'pge',
    bursts: Iterable[str] = None,
    resolution: int = 30,
    container_base_path: Path = Path('/home/rtc_user/scratch'),
):
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
    if bursts is not None:
        runconfig_dict['bursts'] = [b.lower() for b in bursts]

    if config_type not in ['sas', 'pge']:
        raise ValueError('Config type must be sas or pge.')

    template_dir = Path(__file__).parent / 'templates'
    with open(template_dir / f'{config_type}.yml') as file:
        template = Template(file.read())
        template_str = template.render(runconfig_dict)

    with open(config_path, 'w') as file:
        file.write(template_str)


def opera_rtc(
    granules: Iterable[str],
    resolution: int = 30,
    burst_subset: Optional[str] = None,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-1 granules to back-project
        resolution: Resolution of the output RTC (m)
        burst_subset: List of JPL burst ids to process
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    scratch_dir = work_dir / 'scratch' / secrets.token_hex(2)
    input_dir = work_dir / 'input'
    output_dir = work_dir / 'output'
    [d.mkdir(parents=True, exist_ok=True) for d in [scratch_dir, input_dir, output_dir]]

    if all([x.endswith('BURST') for x in granules]):
        granule_path, orbit_path, db_path, dem_path = prep_burst(granules, work_dir=input_dir)
    else:
        if len(granules) > 1:
            raise ValueError('Only one granule is supported for SLC processing')
        granule_path, orbit_path, db_path, dem_path = prep_slc(granules[0], work_dir=input_dir)

    config_path = work_dir / 'runconfig.yml'
    config_args = {
        'config_path': config_path,
        'granule_name': granule_path.name,
        'orbit_name': orbit_path.name,
        'db_name': db_path.name,
        'dem_name': dem_path.name,
        'bursts': burst_subset,
        'resolution': resolution,
    }
    from rtc.core import create_logger
    from rtc.runconfig import RunConfig, load_parameters

    from hyp3_opera_rtc.corvette_opts import RtcOptions
    from hyp3_opera_rtc.corvette_single import run_single_job, split_runconfig

    # Load from run_parallel
    config_args['config_type'] = 'sas'
    config_args['container_base_path'] = input_dir.parent
    render_runconfig(**config_args)
    log_path = str((output_dir / 'rtc.log').resolve())
    create_logger(log_path, full_log_formatting=False)
    cfg = RunConfig.load_from_yaml(str(config_path.resolve()))
    load_parameters(cfg)

    # Spilt into burst configs
    runconfig_burst_list, _ = split_runconfig(cfg, str(output_dir), ['abcd'], str(scratch_dir), str(log_path))

    # Run burst RTC
    cfg = RunConfig.load_from_yaml(runconfig_burst_list[0])
    load_parameters(cfg)
    opts = RtcOptions(dem_path=str(dem_path), output_dir=str(output_dir), scratch_dir=str(scratch_dir))
    run_single_job(cfg.bursts['t115_245714_iw1']['VV'], cfg, opts)


def main():
    """Create an OPERA RTC

    Example commands:
    python -m hyp3_opera_rtc ++process opera_rtc \
        S1A_IW_SLC__1SDV_20240809T141630_20240809T141657_055137_06B825_6B31 --burst-subset t115_245714_iw1

    python -m hyp3_opera_rtc ++process opera_rtc \
        S1_245714_IW1_20240809T141633_VV_6B31-BURST S1_245714_IW1_20240809T141633_VH_6B31-BURST
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granules', nargs='+', help='S1 granule to create an RTC for.')
    parser.add_argument('--resolution', default=30, type=int, help='Resolution of the output RTC (m)')
    parser.add_argument('--burst-subset', nargs='+', type=str, help='JPL burst ids to process')
    parser.add_argument('--work-dir', type=Path, default=None, help='Working directory for processing')

    args = parser.parse_args()

    opera_rtc(**args.__dict__)


if __name__ == '__main__':
    main()
