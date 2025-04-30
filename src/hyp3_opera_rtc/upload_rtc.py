import argparse
import json
from pathlib import Path
from shutil import copyfile, make_archive

import h5py
import lxml.etree as ET
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


def update_hdf5_filenames(hdf5_path: Path, safe: str, calibration: str, noise: str) -> None:
    with h5py.File(hdf5_path, 'r+') as hdf:
        hdf['//metadata/processingInformation/inputs/l1SlcGranules'][()] = [safe]
        hdf['//metadata/processingInformation/inputs/annotationFiles'][()] = [calibration, noise]


def update_xml_filenames(xml_path: Path, safe: str, calibration: str, noise: str) -> None:
    namespaces = {
        'eos': 'http://earthdata.nasa.gov/schema/eos',
        'gco': 'http://www.isotc211.org/2005/gco',
        'gmd': 'http://www.isotc211.org/2005/gmd',
        'gmi': 'http://www.isotc211.org/2005/gmi',
        'gmx': 'http://www.isotc211.org/2005/gmx',
    }
    root = ET.parse(str(xml_path)).getroot()
    xpath_prefix = '//eos:AdditionalAttribute[eos:reference/eos:EOS_AdditionalAttributeDescription/eos:name/gco:'

    xpath_annotation = xpath_prefix + "CharacterString = 'AnnotationFiles']"
    annotations = root.xpath(xpath_annotation, namespaces=namespaces)
    # assert annotations is not None
    assert isinstance(annotations, list) and len(annotations) == 1
    annotation = list(annotations)[0]
    char_string_elem = annotation.find('.//eos:value/gco:CharacterString', namespaces)
    char_string_elem.text = f'["{calibration}", "{noise}"]'

    xpath_safe = xpath_prefix + "CharacterString = 'L1SlcGranules']"
    safe_elems = root.xpath(xpath_safe, namespaces=namespaces)
    assert isinstance(safe_elems, list) and len(safe_elems) == 1
    safe_elem = list(safe_elems)[0]
    char_string_elem = safe_elem.find('.//eos:value/gco:CharacterString', namespaces)
    char_string_elem.text = f'["{safe}"]'

    xpath_input_file = "//gmd:source[gmi:LE_Source/gmd:description/gco:CharacterString = 'GranuleInput']"
    input_file_elems = root.xpath(xpath_input_file, namespaces=namespaces)
    assert isinstance(input_file_elems, list) and len(input_file_elems) == 1
    input_file_elem = list(input_file_elems)[0]
    file_name_pattern = './/gmi:LE_Source/gmd:sourceCitation/gmd:CI_Citation/gmd:title/gmx:FileName'
    file_name_elem = input_file_elem.find(file_name_pattern, namespaces)
    file_name = file_name_elem.get('src')
    new_file_name = '/'.join(file_name.split('/')[:-1] + [safe])
    file_name_elem.set('src', new_file_name)
    file_name_elem.text = file_name_elem.text.replace(file_name, new_file_name)

    ET.ElementTree(root).write(xml_path, pretty_print=True, xml_declaration=True, encoding='UTF-8')


def update_input_filenames(output_dir: Path) -> None:
    file_name_dict = json.loads(str(output_dir / 'input_file.json'))
    safe = file_name_dict['safe']
    calibration = file_name_dict['calibration']
    noise = file_name_dict['noise']

    tifs = list(output_dir.glob('OPERA_L2_RTC-S1*.tif'))
    assert 2 <= len(tifs) <= 3, f'Expected 2 or 3 TIF files, found {len(tifs)}'
    for tif in tifs:
        update_image_filenames(tif, safe, calibration, noise)

    hdf5_files = list(output_dir.glob('OPERA_L2_RTC-S1*.h5'))
    assert len(hdf5_files) == 1, f'Expected 1 HDF5 file, found {len(hdf5_files)}'
    update_hdf5_filenames(hdf5_files[0], safe, calibration, noise)

    xml_files = list(output_dir.glob('OPERA_L2_RTC-S1*.iso.xml'))
    assert len(xml_files) == 1, f'Expected 1 XML file, found {len(xml_files)}'
    update_xml_filenames(xml_files[0], safe, calibration, noise)


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
