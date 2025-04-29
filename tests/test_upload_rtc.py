from pathlib import Path
from zipfile import ZipFile

import pytest
from hyp3lib import aws
from moto import mock_aws
from moto.core import patch_client

from hyp3_opera_rtc.upload_rtc import make_zip_name, upload_rtc


def test_upload_rtc(rtc_results_dir, rtc_output_files, s3_bucket):
    prefix = 'myPrefix'

    upload_rtc(s3_bucket, prefix, rtc_results_dir)

    resp = aws.S3_CLIENT.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)

    assert len(resp['Contents']) == 9

    product_name = 'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0'
    zip_s3_key = [c['Key'] for c in resp['Contents'] if c['Key'].endswith('.zip')].pop()
    assert Path(zip_s3_key).name == f'{product_name}.zip'

    zip_download_path = rtc_results_dir / 'output.zip'
    aws.S3_CLIENT.download_file(s3_bucket, zip_s3_key, zip_download_path)

    with ZipFile(zip_download_path) as zf:
        files_in_zip = set([f.filename for f in zf.infolist()])

        assert files_in_zip == set([
            f'{product_name}/',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_BROWSE.png',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.iso.xml',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.h5',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_mask.tif',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VH.tif',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VV.tif',
        ])


def test_make_zip_name(rtc_output_files):
    zip_filename = make_zip_name([Path(f) for f in rtc_output_files])

    assert zip_filename == 'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0'


@pytest.fixture
def rtc_results_dir(tmp_path, rtc_output_files):
    (tmp_path / 'burst-dir').mkdir(parents=True)

    for file in rtc_output_files:
        (tmp_path / file).touch()

    return tmp_path


@pytest.fixture
def rtc_output_files():
    return [
        'OPERA_L2_RTC-S1_20250411T185446Z_S1A_30_v1.0.catalog.json',
        'OPERA_L2_RTC-S1_20250411T185446Z_S1A_30_v1.0.log',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.iso.xml',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_BROWSE.png',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.h5',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_mask.tif',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VH.tif',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VV.tif',
    ]


@pytest.fixture
def s3_bucket():
    with mock_aws():
        patch_client(aws.S3_CLIENT)

        bucket_name = 'myBucket'
        location = {'LocationConstraint': 'us-west-2'}

        aws.S3_CLIENT.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=location)

        yield bucket_name
