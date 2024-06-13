import argparse
from pathlib import Path
from typing import Iterable, Optional

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
    }
    if bursts is not None:
        runconfig_dict['bursts'] = [b.lower() for b in bursts]

    if config_type not in ['sas', 'pge']:
        raise ValueError('Config type must be sas or pge.')

    template_dir = Path(__file__).parent / 'templates'
    with open(template_dir / f'{config_type}.yml', 'r') as file:
        template = Template(file.read())
        template_str = template.render(runconfig_dict)

    with open(config_path, 'w') as file:
        file.write(template_str)


def opera_rtc(
    granules: Iterable[str],
    burst_subset: Optional[str] = None,
    use_resorb: bool = True,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-1 granules to back-project
        bursts: List of JPL burst ids to process
        use_resorb: Use the RESORB orbits instead of the POEORB orbits
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    scratch_dir = work_dir / 'scratch'
    input_dir = work_dir / 'input'
    output_dir = work_dir / 'output'
    [d.mkdir(parents=True, exist_ok=True) for d in [scratch_dir, input_dir, output_dir]]

    if all([x.endswith('BURST') for x in granules]):
        granule_path, orbit_path, db_path, dem_path = prep_burst(granules, use_resorb=use_resorb, work_dir=input_dir)
    else:
        if len(granules) > 1:
            raise ValueError('Only one granule is supported for SLC processing')
        granule_path, orbit_path, db_path, dem_path = prep_slc(granules[0], use_resorb=use_resorb, work_dir=input_dir)

    config_path = work_dir / 'runconfig.yml'
    config_args = {
        'config_path': config_path,
        'granule_name': granule_path.name,
        # 'orbit_name': orbit_path.name,
        'orbit_name': 'S1A_OPER_AUX_RESORB_OPOD_20240605T154014_V20240605T115029_20240605T150759.EOF',
        'db_name': db_path.name,
        'dem_name': dem_path.name,
        'bursts': burst_subset,
    }
    pge_present = False
    try:
        from opera.scripts.pge_main import pge_start

        pge_present = True
        config_args['config_type'] = 'pge'
        render_runconfig(**config_args)
        pge_start(str(config_path.resolve()))
    except ImportError:
        print('OPERA PGE script is not present, using OPERA SAS library.')

    rtc_present = False
    try:
        import logging

        from rtc.core import create_logger
        from rtc.rtc_s1 import run_parallel
        from rtc.rtc_s1_single_job import get_rtc_s1_parser
        from rtc.runconfig import RunConfig, load_parameters

        rtc_present = True
        config_args['config_type'] = 'sas'
        config_args['container_base_path'] = input_dir.parent
        render_runconfig(**config_args)
        log_path = str((output_dir / 'rtc.log').resolve())
        create_logger(log_path, full_log_formatting=False)
        cfg = RunConfig.load_from_yaml(str(config_path.resolve()))
        load_parameters(cfg)
        run_parallel(cfg, logfile_path=log_path, full_log_formatting=False)
    except ImportError:
        pass

    if not pge_present and not rtc_present:
        raise ImportError('Neither the OPERA RTC PGE or SAS modules could be imported.')


def main():
    """Create an OPERA RTC

    Example command:
    python -m hyp3_opera_rtc ++process opera_rtc S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granules', nargs='+', help='S1 granule to create an RTC for.')
    parser.add_argument('--burst-subset', nargs='+', type=str, help='JPL burst ids to process')
    parser.add_argument('--use-resorb', action='store_true', help='Use RESORB orbits instead of POEORB')
    parser.add_argument('--work-dir', type=Path, default=None, help='Working directory for processing')

    args = parser.parse_args()

    opera_rtc(**args.__dict__)


if __name__ == '__main__':
    main()
