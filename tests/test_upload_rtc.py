import json
import shutil
from collections import Counter
from pathlib import Path
from unittest.mock import call, patch
from zipfile import ZipFile

import pytest
from hyp3lib import aws
from moto import mock_aws
from moto.core import patch_client

import hyp3_opera_rtc
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

        assert files_in_zip == {
            f'{product_name}/',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_BROWSE.png',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.iso.xml',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0.h5',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_mask.tif',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VH.tif',
            f'{product_name}/OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0_VV.tif',
        }


def test_upload_slc_rtc(rtc_slc_results_dir, s3_bucket):
    prefix = 'myPrefix'
    upload_rtc.upload_rtc(s3_bucket, prefix, rtc_slc_results_dir)

    resp = aws.S3_CLIENT.list_objects_v2(Bucket=s3_bucket, Prefix=prefix)

    zip_s3_keys = [c['Key'] for c in resp['Contents'] if c['Key'].endswith('.zip')]
    assert len(zip_s3_keys) == 0

    uploaded_files = [c['Key'] for c in resp['Contents']]

    assert len(uploaded_files) == 164
    file_suffixs = dict(Counter(Path(f).suffix for f in uploaded_files))
    assert file_suffixs == {'.json': 1, '.log': 1, '.h5': 27, '.xml': 27, '.png': 27, '.tif': 27 * 3}


def test_make_zip_name(rtc_burst_output_files):
    zip_filename = upload_rtc.make_zip_name([Path(f) for f in rtc_burst_output_files])

    assert zip_filename == 'OPERA_L2_RTC-S1_T115-245714-IW1_20240809T141633Z_20250411T185446Z_S1A_30_v1.0'


@patch('hyp3_opera_rtc.upload_rtc.update_xml_with_asf_lineage')
def test_update_xmls_with_slc_results(update_mock, rtc_slc_results_dir):
    upload_rtc.update_xmls_with_asf_lineage(rtc_slc_results_dir)

    assert len(update_mock.call_args_list) == 27
    assert all(call[0][0].suffix == '.xml' for call in update_mock.call_args_list)


@patch('hyp3_opera_rtc.upload_rtc.update_xml_with_asf_lineage')
def test_update_xmls(update_mock, tmp_path):
    upload_rtc.update_xmls_with_asf_lineage(tmp_path)
    update_mock.assert_not_called()

    for file in ['f.txt', 'f.xml', 'f.json', 'f2.xml']:
        (tmp_path / file).touch()

    upload_rtc.update_xmls_with_asf_lineage(tmp_path)
    calls = [call(tmp_path / 'f.xml'), call(tmp_path / 'f2.xml')]
    update_mock.assert_has_calls(calls, any_order=True)


@patch.object(hyp3_opera_rtc, '__version__', '1.0.0')
def test_get_xml_with_asf_lineage(iso_xml_path, updated_xml_path):
    upload_rtc.update_xml_with_asf_lineage(iso_xml_path)

    with updated_xml_path.open() as expected_file, iso_xml_path.open() as xml_file:
        expected = expected_file.read()
        updated = xml_file.read()

        assert expected == updated



def test_cant_find_lineage_in_xml(tmp_path):
    xml_path = tmp_path / 'f.xml'
    with xml_path.open(mode='w') as f:
        f.write('<bad><xml><structure></structure></xml></bad>')

    with pytest.raises(upload_rtc.FailedToFindLineageStatementError):
        upload_rtc.update_xml_with_asf_lineage(xml_path)


@pytest.fixture
def iso_xml_path(tmp_path):
    xml_output_path = tmp_path / 'opera_v1.0.iso.xml'
    shutil.copy(Path(__file__).parent / 'data' / 'opera_v1.0.iso.xml', xml_output_path)

    return xml_output_path


@pytest.fixture
def updated_xml_path(tmp_path):
    xml_output_path = tmp_path / 'updated-opera_v1.0.iso.xml'
    shutil.copy(Path(__file__).parent / 'data' / 'updated-opera_v1.0.iso.xml', xml_output_path)

    return xml_output_path


@pytest.fixture
def rtc_burst_results_dir(tmp_path, rtc_burst_output_files):
    (tmp_path / 'burst-dir').mkdir(parents=True)

    for file in rtc_burst_output_files:
        (tmp_path / file).touch()

    return tmp_path


@pytest.fixture
def rtc_slc_results_dir(tmp_path, rtc_slc_output_files):
    (tmp_path / 'slc-dir').mkdir(parents=True)

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
