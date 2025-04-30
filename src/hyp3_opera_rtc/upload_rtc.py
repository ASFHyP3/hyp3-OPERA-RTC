import argparse
import json
from pathlib import Path
from shutil import copyfile, make_archive

import h5py
from hyp3lib.aws import upload_file_to_s3
from osgeo import gdal


gdal.UseExceptions()


def update_image_filenames(image_path: Path, safe: str, calibration: str, noise: str) -> None:
    ds = gdal.Open(str(image_path), gdal.GA_Update)
    metadata = ds.GetMetadata()
    metadata['INPUT_L1_SLC_GRANULES'] = [safe]
    metadata['INPUT_ANNOTATION_FILES'] = [calibration, noise]
    ds.SetMetadata(metadata)
    ds.FlushCache()
    ds = None


def update_input_filenames(output_dir: Path) -> None:
    file_name_dict = json.load(output_dir / 'input_file.json')
    tifs = list(output_dir.glob('OPERA_L2_RTC-S1*.tif'))
    safe = file_name_dict['safe']
    calibration = file_name_dict['calibration']
    noise = file_name_dict['noise']
    [update_image_filenames(tif, safe, calibration, noise) for tif in tifs]

    metadata_hdf5 = list(output_dir.glob('OPERA_L2_RTC-S1*.h5'))[0]
    with h5py.File(metadata_hdf5, 'r+') as hdf:
        hdf['//metadata/processingInformation/inputs/l1SlcGranules'] = safe
        hdf['//metadata/processingInformation/inputs/annotationFiles'] = [calibration, noise]


def upload_rtc(bucket: str, bucket_prefix: str, output_dir: Path) -> None:
    output_files = [f for f in output_dir.iterdir() if not f.is_dir()]

    output_zip = make_zip(output_files, output_dir)

    for output_file in output_files + [output_zip]:
        upload_file_to_s3(output_file, bucket, bucket_prefix)


def make_zip(output_files: list[Path], output_dir: Path) -> Path:
    zip_archive_path = output_dir / 'zip'
    zip_archive_path.mkdir(exist_ok=True)

    for output_file in output_files:
        copyfile(output_file, zip_archive_path / output_file.name)

    zip_path = output_dir / make_zip_name(output_files)
    output_zip = make_archive(base_name=str(zip_path), format='zip', root_dir=zip_archive_path)

    return Path(output_zip)


def make_zip_name(product_files: list[Path]) -> str:
    h5_file = [f for f in product_files if f.name.endswith('h5')].pop()
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
