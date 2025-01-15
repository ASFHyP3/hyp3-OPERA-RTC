"""OPERA-RTC processing for HyP3"""

import argparse
import sys
from importlib.metadata import entry_points


def main():
    """Main entrypoint for HyP3 processing

    Calls the HyP3 entrypoint specified by the `++process` argument
    """
    parser = argparse.ArgumentParser(prefix_chars='+', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '++process',
        choices=['prep_burst', 'prep_slc', 'opera_rtc'],
        default='opera_rtc',
        help='Select the HyP3 entrypoint to use',  # HyP3 entrypoints are specified in `pyproject.toml`
    )

    args, unknowns = parser.parse_known_args()
    all_entry_points = entry_points()
    hyp3_entry_points = [ep for ep in all_entry_points['hyp3'] if ep.name == args.process]

    if not hyp3_entry_points:
        print(f'No entry point found for {args.process}')
        sys.exit(1)

    process_entry_point = hyp3_entry_points[0]

    sys.argv = [args.process, *unknowns]
    sys.exit(process_entry_point.load()())


if __name__ == '__main__':
    main()
