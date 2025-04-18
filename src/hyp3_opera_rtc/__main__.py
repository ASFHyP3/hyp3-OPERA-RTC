import argparse
import os
import subprocess
import warnings
from pathlib import Path

from hyp3lib.fetch import write_credentials_to_netrc_file

from hyp3_opera_rtc.prep_rtc import prep_rtc
from hyp3_opera_rtc.upload_rtc import upload_rtc


def main() -> None:
    """Prepare, processes and upload results for OPERA RTC.

    Example commands:
    python -m hyp3_opera_rtc \
        S1_245714_IW1_20240809T141633_VV_6B31-BURST S1_245714_IW1_20240809T141633_VH_6B31-BURST
        --bucket myBucket \
        --bucket-prefix myPrefix
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('granules', nargs='+', help='Sentinel-1 VV burst granules to download input data for.')
    parser.add_argument('--resolution', default=30, type=int, help='Resolution of the output RTC (m)')
    parser.add_argument('--work-dir', type=Path, default=None, help='Working directory for processing')
    parser.add_argument('--bucket', help='AWS S3 bucket HyP3 uses for uploading the final products')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to products')

    args = parser.parse_args()

    username = os.getenv('EARTHDATA_USERNAME')
    password = os.getenv('EARTHDATA_PASSWORD')
    if username and password:
        write_credentials_to_netrc_file(username, password, append=False)

    if not (Path.home() / '.netrc').exists():
        warnings.warn(
            'Earthdata credentials must be present as environment variables, or in your netrc.',
            UserWarning,
        )

    if args.work_dir is None:
        args.work_dir = Path.cwd()

    prep_rtc(args.granules, args.work_dir, args.resolution)

    cmd = [
        'conda',
        'run',
        '-n',
        'RTC',
        '/home/rtc_user/opera/scripts/pge_main.py',
        '-f',
        '/home/rtc_user/scratch/runconfig.yml',
    ]
    subprocess.run(cmd, check=True)

    if not args.bucket:
        print('No bucket provided, skipping upload')
    else:
        print(f'Uploading outputs to {args.bucket}')
        upload_rtc(args.bucket, args.bucket_prefix, args.work_dir / 'output')


if __name__ == '__main__':
    main()
