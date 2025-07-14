import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from hyp3lib import aws
from moto import mock_aws
from moto.core import patch_client

from hyp3_opera_rtc import upload_rtc


def test_upload_burst_rtc(rtc_burst_results_dir, s3_bucket):
    prefix = 'myPrefix'
    upload_rtc.upload_rtc(s3_bucket, prefix, rtc_burst_results_dir)

    resp = aws.S3_CLIENT.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)

    assert len(resp['Contents']) == 9

    product_name = 'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0'
    zip_s3_key = [c['Key'] for c in resp['Contents'] if c['Key'].endswith('.zip')].pop()
    zip_filename = zip_s3_key.split(f'{prefix}/').pop()

    assert zip_filename == f'{product_name}.zip'

    zip_download_path = rtc_burst_results_dir / 'output.zip'
    aws.S3_CLIENT.download_file(s3_bucket, zip_s3_key, zip_download_path)

    with ZipFile(zip_download_path) as zf:
        files_in_zip = set([f.filename for f in zf.infolist()])

        assert files_in_zip == set(
            [
                f'{product_name}/',
                f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_BROWSE.png',
                f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.iso.xml',
                f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.h5',
                f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_mask.tif',
                f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VH.tif',
                f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VV.tif',
            ]
        )


def test_upload_slc_rtc(rtc_slc_results_dir, s3_bucket):
    prefix = 'myPrefix'
    upload_rtc.upload_rtc(s3_bucket, prefix, rtc_slc_results_dir)

    resp = aws.S3_CLIENT.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)

    zip_s3_keys = [c['Key'] for c in resp['Contents'] if c['Key'].endswith('.zip')]
    assert len(zip_s3_keys) == 27
    assert all(zip_key.endswith('.zip') for zip_key in zip_s3_keys)

    for zip_key in zip_s3_keys:
        zip_download_path = rtc_slc_results_dir / 'output.zip'
        aws.S3_CLIENT.download_file(s3_bucket, zip_key, zip_download_path)

        with ZipFile(zip_download_path) as zf:
            files_in_zip = [f.filename for f in zf.infolist()]
            assert len(files_in_zip) == 7

            product_name = files_in_zip[0].split('/')[0]
            assert all(f.startswith(f'{product_name}/') for f in files_in_zip)

            file_suffixs = set(Path(f).suffix for f in files_in_zip)
            assert file_suffixs == {'.0', '.xml', '.tif', '.h5', '.png'}


def test_make_zip_name(rtc_burst_output_files):
    zip_filename = upload_rtc.make_zip_name([Path(f) for f in rtc_burst_output_files])

    assert zip_filename == 'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0'


def test_make_zip_groups(rtc_slc_output_files, rtc_slc_results_dir):
    result_paths = [rtc_slc_results_dir / f for f in rtc_slc_output_files]
    upload_rtc.make_zip_groups(result_paths)


@pytest.fixture
def rtc_burst_results_dir(tmp_path, rtc_burst_output_files):
    (tmp_path / 'burst-dir').mkdir(parents=True)

    for file in rtc_burst_output_files:
        (tmp_path / file).touch()

    return tmp_path


@pytest.fixture
def rtc_slc_results_dir(tmp_path, rtc_slc_output_files):
    (tmp_path / 'burst-dir').mkdir(parents=True)

    for file in rtc_slc_output_files:
        (tmp_path / file).touch()

    return tmp_path


@pytest.fixture
def rtc_burst_output_files():
    with (Path(__file__).parent / 'data' / 'rtc_output_files.json').open() as f:
        return json.load(f)['burst']


@pytest.fixture
def rtc_slc_output_files():
    with (Path(__file__).parent / 'data' / 'rtc_output_files.json').open() as f:
        return json.load(f)['slc']


@pytest.fixture
def s3_bucket():
    with mock_aws():
        patch_client(aws.S3_CLIENT)

        bucket_name = 'myBucket'
        location = {'LocationConstraint': 'us-west-2'}

        aws.S3_CLIENT.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=location)

        yield bucket_name
