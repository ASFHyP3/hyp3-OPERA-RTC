import json
import unittest.mock
from pathlib import Path
from shutil import copyfile

import pytest
import requests
import responses

from hyp3_opera_rtc import prep_rtc


def test_create_file_input_json(tmp_path):
    tmp_dir = tmp_path / 'input'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    test_xml = Path('tests/data/S1A_IW_SLC__1SDV_20250413T020809_20250413T020836_058732_07464F_EF1E_VV.xml')
    copyfile(test_xml, tmp_dir / test_xml.name)
    output_json = tmp_dir / 'input_file.json'

    prep_rtc.create_input_file_json(tmp_dir, 'IW2', output_json)
    assert output_json.exists()

    input_files = json.loads(output_json.read_text())
    assert input_files['safe'] == 'S1A_IW_SLC__1SDV_20250413T020809_20250413T020836_058732_07464F_EF1E.zip'
    assert input_files['noise'] == 'noise-s1a-iw2-slc-vv-20250413t020809-20250413t020834-058732-07464f-005.xml'
    assert (
        input_files['calibration'] == 'calibration-s1a-iw2-slc-vv-20250413t020809-20250413t020834-058732-07464f-005.xml'
    )


@responses.activate
def test_granule_exists():
    responses.get(
        url=prep_rtc.CMR_URL,
        match=[
            responses.matchers.query_param_matcher(
                {'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'S1_073251_IW2_20250413T020809_VV_EF1E-BURST'}
            )
        ],
        json={'items': ['foo']},
    )
    responses.get(
        url=prep_rtc.CMR_URL,
        match=[
            responses.matchers.query_param_matcher(
                {'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'S1_073251_IW2_20250413T020809_VH_EF1E-BURST'}
            )
        ],
        json={'items': []},
    )
    responses.get(
        url=prep_rtc.CMR_URL,
        match=[responses.matchers.query_param_matcher({'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'foo'})],
        status=400,
    )

    assert prep_rtc.granule_exists('S1_073251_IW2_20250413T020809_VV_EF1E-BURST')

    assert not prep_rtc.granule_exists('S1_073251_IW2_20250413T020809_VH_EF1E-BURST')

    with pytest.raises(requests.HTTPError):
        prep_rtc.granule_exists('foo')


def test_validate_co_pol_granule():
    def mock_granule_exists(granule: str) -> bool:
        return granule in [
            'S1_146160_IW1_20241029T095958_VV_592B-BURST',
            'S1_152193_IW3_20250415T143714_HH_EF65-BURST',
        ]

    with unittest.mock.patch('hyp3_opera_rtc.prep_rtc.granule_exists', mock_granule_exists):
        prep_rtc.validate_co_pol_granule('S1_146160_IW1_20241029T095958_VV_592B-BURST')
        prep_rtc.validate_co_pol_granule('S1_152193_IW3_20250415T143714_HH_EF65-BURST')

        with pytest.raises(
            ValueError, match=r'^S1_073251_IW2_20250413T020809_VH_EF1E-BURST has polarization VH, must be VV or HH'
        ):
            prep_rtc.validate_co_pol_granule('S1_073251_IW2_20250413T020809_VH_EF1E-BURST')

        with pytest.raises(
            ValueError, match=r'^S1_241258_IW1_20250418T105137_HV_57A0-BURST has polarization HV, must be VV or HH'
        ):
            prep_rtc.validate_co_pol_granule('S1_241258_IW1_20250418T105137_HV_57A0-BURST')

        with pytest.raises(ValueError, match=r'^Granule does not exist: S1_073251_IW2_20250413T020809_VV_EF1E-BURST$'):
            prep_rtc.validate_co_pol_granule('S1_073251_IW2_20250413T020809_VV_EF1E-BURST')


def test_get_cross_pol_name():
    assert (
        prep_rtc.get_cross_pol_name('S1_073251_IW2_20250413T020809_VV_EF1E-BURST')
        == 'S1_073251_IW2_20250413T020809_VH_EF1E-BURST'
    )
    assert (
        prep_rtc.get_cross_pol_name('S1_241258_IW1_20250418T105137_HH_57A0-BURST')
        == 'S1_241258_IW1_20250418T105137_HV_57A0-BURST'
    )
    with pytest.raises(KeyError, match=r"^'VH'$"):
        prep_rtc.get_cross_pol_name('S1_073251_IW2_20250413T020809_VH_EF1E-BURST')
