"""OPERA-RTC processing for HyP3."""

import argparse
import os
import sys
import warnings
from importlib.metadata import entry_points
from pathlib import Path

from hyp3lib.fetch import write_credentials_to_netrc_file


def main() -> None:
    """Main entrypoint for HyP3 processing.

    Calls the HyP3 entrypoint specified by the `++process` argument
    """
    parser = argparse.ArgumentParser(prefix_chars='+', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '++process',
        choices=['prep_burst', 'prep_slc', 'prep_rtc', 'upload_rtc'],
        help='Select the HyP3 entrypoint to use',  # HyP3 entrypoints are specified in `pyproject.toml`
    )

    args, unknowns = parser.parse_known_args()
    hyp3_entry_points = entry_points(group='hyp3', name=args.process)

    username = os.getenv('EARTHDATA_USERNAME')
    password = os.getenv('EARTHDATA_PASSWORD')
    if username and password:
        write_credentials_to_netrc_file(username, password, append=False)

    if not (Path.home() / '.netrc').exists():
        warnings.warn(
            'Earthdata credentials must be present as environment variables, or in your netrc.',
            UserWarning,
        )

    if not hyp3_entry_points:
        print(f'No entry point found for {args.process}')
        sys.exit(1)

    process_entry_point = list(hyp3_entry_points)[0]

    sys.argv = [args.process, *unknowns]
    sys.exit(process_entry_point.load()())


if __name__ == '__main__':
    main()
