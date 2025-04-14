import argparse
from pathlib import Path

from hyp3lib.aws import upload_file_to_s3
from hyp3lib.image import create_thumbnail


def upload_rtc(bucket: str, bucket_prefix: str, work_dir: Path) -> None:
    for browse in work_dir.glob('*.png'):
        create_thumbnail(browse, output_dir=work_dir)

    for product_file in work_dir.iterdir():
        if product_file.is_dir():
            continue

        upload_file_to_s3(product_file, bucket, bucket_prefix)


def main() -> None:
    """Upload results of OPERA RTC.

    Example commands:
    python -m hyp3_opera_rtc ++process upload_rtc \
        --bucket myBucket \
        --bucket-prefix myPrefix
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--bucket', required=True, help='AWS S3 bucket HyP3 uses for uploading the final products')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to products')
    parser.add_argument('--work-dir', type=Path, default=Path(), help='directory with processing outputs')

    args = parser.parse_args()

    upload_rtc(**args.__dict__)
    print(args)
