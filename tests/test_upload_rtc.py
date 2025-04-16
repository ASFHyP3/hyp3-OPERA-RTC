import pytest
from hyp3lib import aws
from moto import mock_aws
from moto.core import patch_client

from hyp3_opera_rtc.upload_rtc import upload_rtc


def test_upload_rtc(rtc_results_dir, s3_bucket):
    prefix = 'myPrefix'

    upload_rtc(s3_bucket, prefix, rtc_results_dir)

    resp = aws.S3_CLIENT.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)

    assert len(resp['Contents']) == 9
    assert len([c['Key'] for c in resp['Contents'] if c['Key'].endswith('.zip')]) == 1


@pytest.fixture
def rtc_results_dir(tmp_path):
    files = [
        'OPERA_L2_RTC-S1_20250411T185446Z_S1A_30_v1.0.catalog.json',
        'OPERA_L2_RTC-S1_20250411T185446Z_S1A_30_v1.0.log',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.iso.xml',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_BROWSE.png',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.h5',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_mask.tif',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VH.tif',
        'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VV.tif',
    ]

    (tmp_path / 'burst-dir').mkdir(parents=True)

    for file in files:
        (tmp_path / file).touch()

    return tmp_path


@pytest.fixture
def s3_bucket():
    with mock_aws():
        patch_client(aws.S3_CLIENT)

        bucket_name = 'myBucket'
        location = {'LocationConstraint': 'us-west-2'}

        aws.S3_CLIENT.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=location)

        yield bucket_name
