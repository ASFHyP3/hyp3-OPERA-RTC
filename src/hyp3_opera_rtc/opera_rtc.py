import argparse
from pathlib import Path
from typing import Optional

from jinja2 import Template

from hyp3_opera_rtc.prep_slc import prep_slc


def render_runconfig(
    config_path: Path,
    granule_path: Path,
    orbit_path: Path,
    db_path: Path,
    dem_path: Path,
    scratch_dir: Path,
    output_dir: Path,
):
    runconfig_dict = {
        'granule_path': str(granule_path),
        'orbit_path': str(orbit_path),
        'db_path': str(db_path),
        'dem_path': str(dem_path),
        'scratch_dir': str(scratch_dir),
        'output_dir': str(output_dir),
    }

    template_dir = Path(__file__).parent / 'templates'
    with open(template_dir / 'runconfig.yml', 'r') as file:
        template = Template(file.read())
        template_str = template.render(runconfig_dict)

    with open(config_path, 'w') as file:
        file.write(template_str)


def opera_rtc(
    granule: str,
    use_resorb: bool = True,
    work_dir: Optional[Path] = None,
) -> Path:
    """Prepare data for SLC-based processing.

    Args:
        granules: List of Sentinel-1 level-0 granules to back-project
        use_resorb: Use the RESORB orbits instead of the POEORB orbits
        work_dir: Working directory for processing
    """
    if work_dir is None:
        work_dir = Path.cwd()

    scratch_dir = work_dir / 'scratch'
    input_dir = work_dir / 'input'
    output_dir = work_dir / 'output'
    [d.mkdir(parents=True, exist_ok=True) for d in [scratch_dir, input_dir, output_dir]]
    granule_path, orbit_path, db_path, dem_path = prep_slc(granule, use_resorb=use_resorb, work_dir=input_dir)
    config_path = work_dir / 'runconfig.yml'
    render_runconfig(config_path, granule_path, orbit_path, db_path, dem_path, scratch_dir, output_dir)


def main():
    """Create an OPERA RTC

    Example command:
    python -m hyp3_opera_rtc ++process opera_rtc S1B_IW_SLC__1SDV_20180504T104507_20180504T104535_010770_013AEE_919F
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granule', help='S1 granule to create an RTC for.')
    parser.add_argument(
        '--use-resorb',
        action='store_true',
        help='Use RESORB orbits instead of POEORB orbits',
    )
    parser.add_argument('--work-dir', default=None, help='Working directory for processing')

    args = parser.parse_args()

    opera_rtc(**args.__dict__)


if __name__ == '__main__':
    main()
