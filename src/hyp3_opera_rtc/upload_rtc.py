import argparse
from pathlib import Path
from shutil import copyfile, make_archive
from xml.etree import ElementTree as et

from hyp3lib.aws import upload_file_to_s3

import hyp3_opera_rtc


class FailedToFindLineageStatementError(Exception):
    pass


def upload_rtc(bucket: str, bucket_prefix: str, output_dir: Path) -> None:
    output_files = [f for f in output_dir.iterdir() if not f.is_dir()]

    burst_count = len([f for f in output_files if f.name.endswith('h5')])
    if burst_count == 1:
        output_zip = make_zip(output_files, output_dir)
        output_files.append(output_zip)

    for output_file in output_files:
        upload_file_to_s3(output_file, bucket, bucket_prefix, chunk_size=100_000_000)


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


def update_xmls_with_asf_lineage(output_dir: Path) -> None:
    xml_paths = [f for f in output_dir.iterdir() if f.suffix == '.xml']

    for xml_path in xml_paths:
        update_xml_with_asf_lineage(xml_path)


def update_xml_with_asf_lineage(xml_path: Path) -> None:
    iso_tree = et.parse(str(xml_path))

    gmd = '{http://www.isotc211.org/2005/gmd}'
    gco = '{http://www.isotc211.org/2005/gco}'
    lineage_tag_path = f'.//{gmd}LI_Lineage/{gmd}statement/{gco}CharacterString'

    lineage_search = iso_tree.findall(lineage_tag_path)
    if len(lineage_search) == 0:
        raise FailedToFindLineageStatementError('Failed to find lineage statement in iso xml')

    lineage = lineage_search[0]
    version = hyp3_opera_rtc.__version__
    assert lineage.text is not None

    old_lineage = lineage.text
    new_lineage = f'{old_lineage.replace("JPL", "ASF")} via HyP3 OPERA-RTC v{version}'

    with xml_path.open('r+') as f:
        xml_text = f.read()
        f.seek(0)

        updated_xml = xml_text.replace(old_lineage, new_lineage)
        f.write(updated_xml)


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
    update_xmls_with_asf_lineage(args.output_dir)

    if not args.bucket:
        print('No bucket provided, skipping upload')
    else:
        print(f'Uploading outputs to {args.bucket}')
        upload_rtc(args.bucket, args.bucket_prefix, args.output_dir)


if __name__ == '__main__':
    main()
