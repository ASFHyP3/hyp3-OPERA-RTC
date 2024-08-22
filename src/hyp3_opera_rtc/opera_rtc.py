import argparse
from pathlib import Path
from typing import Iterable, Optional

from jinja2 import Template

from hyp3_opera_rtc.prep_slc import prep_slc


def render_runconfig(
    config_path: Path,
    granule_name: str,
    orbit_name: str,
    db_name: str,
    dem_name: str,
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

    template_dir = Path(__file__).parent / 'templates'
    with open(template_dir / 'runconfig.yml', 'r') as file:
        template = Template(file.read())
        template_str = template.render(runconfig_dict)

    with open(config_path, 'w') as file:
        file.write(template_str)


def opera_rtc(
    granule: str,
    bursts: Optional[str] = None,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-0 granules to back-project
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    scratch_dir = work_dir / 'scratch'
    input_dir = work_dir / 'input'
    output_dir = work_dir / 'output'
    [d.mkdir(parents=True, exist_ok=True) for d in [scratch_dir, input_dir, output_dir]]
    granule_path, orbit_path, db_path, dem_path = prep_slc(granule, work_dir=input_dir)
    config_path = work_dir / 'runconfig.yml'
    render_runconfig(config_path, granule_path.name, orbit_path.name, db_path.name, dem_path.name, bursts)

    try:
        from opera.scripts.pge_main import pge_start
    except ImportError:
        raise ImportError('OPERA PGE script is not present. Are you running from within the OPERA PGE container?')

    pge_start(str(config_path.resolve()))


def main():
    """Create an OPERA RTC

    Example command:
    python -m hyp3_opera_rtc ++process opera_rtc \
        S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F --bursts 069_147178_IW3
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granule', type=str, help='S1 granule to create an RTC for.')
    parser.add_argument('--bursts', nargs='+', type=str, help='JPL burst id to process')
    parser.add_argument('--work-dir', type=Path, default=None, help='Working directory for processing')

    args = parser.parse_args()

    opera_rtc(**args.__dict__)


if __name__ == '__main__':
    main()
