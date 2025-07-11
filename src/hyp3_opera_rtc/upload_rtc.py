import argparse
from pathlib import Path
from shutil import copyfile, make_archive

from hyp3lib.aws import upload_file_to_s3


def upload_rtc(bucket: str, bucket_prefix: str, output_dir: Path) -> None:
    output_files = [f for f in output_dir.iterdir() if not f.is_dir()]

    zip_groups = make_zip_groups(output_files)
    output_zips = [make_zip(zip_group, output_dir / group_name) for group_name, zip_group in zip_groups.items()]

    for output_file in output_files + output_zips:
        upload_file_to_s3(output_file, bucket, bucket_prefix)


def make_zip_groups(output_files: list[Path]) -> dict[str, list[Path]]:
    zip_group_names = [file.name.split('.h5')[0] for file in output_files if file.name.endswith('h5')]
    zip_groups = {}

    for zip_group_name in zip_group_names:
        zip_group = [output_file for output_file in output_files if zip_group_name in output_file.name]
        zip_groups[zip_group_name] = zip_group

    return zip_groups


def make_zip(output_files: list[Path], output_dir: Path) -> Path:
    zip_name = make_zip_name(output_files)
    zip_path = output_dir / zip_name

    zip_archive_path = output_dir / 'zip'
    (zip_archive_path / zip_name).mkdir(exist_ok=True, parents=True)

    file_extensions_to_include = set(['.png', '.xml', '.tif', '.h5'])
    for output_file in output_files:
        if output_file.suffix not in file_extensions_to_include:
            continue

        zip_dest_path = zip_archive_path / zip_name / output_file.name
        copyfile(output_file, zip_dest_path)

    output_zip = make_archive(base_name=str(zip_path), format='zip', root_dir=zip_archive_path)
    return Path(output_zip)


def make_zip_name(product_files: list[Path]) -> str:
    h5_file = [f for f in product_files if f.name.endswith('h5')][0]

    return h5_file.name.split('.h5')[0]


def main() -> None:
    """Upload results of OPERA RTC.

    Example commands:
    python -m hyp3_opera_rtc.upload_rtc \
        --bucket myBucket \
        --bucket-prefix myPrefix
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--output-dir', type=Path, required=True, help='Directory containing processing outputs')
    parser.add_argument('--bucket', help='AWS S3 bucket HyP3 uses for uploading the final products')
    parser.add_argument('--bucket-prefix', default='', help='Add a bucket prefix to products')

    args, _ = parser.parse_known_args()

    if not args.bucket:
        print('No bucket provided, skipping upload')
    else:
        print(f'Uploading outputs to {args.bucket}')
        upload_rtc(args.bucket, args.bucket_prefix, args.output_dir)


if __name__ == '__main__':
    main()
