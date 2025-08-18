import json
from pathlib import Path

import pytest
import requests
import responses

from hyp3_opera_rtc import prep_rtc


def test_parse_response_for_params():
    test_response = json.loads((Path(__file__).parent / 'data' / 'burst_response.json').read_text())
    slc_name, burst_id = prep_rtc.parse_response_for_burst_params(test_response)
    assert slc_name == 'S1A_IW_SLC__1SDV_20250413T020809_20250413T020836_058732_07464F_EF1E'
    assert burst_id == 't035_073251_iw2'


@responses.activate
def test_get_burst_from_cmr():
    responses.get(
        url=prep_rtc.CMR_URL,
        match=[
            responses.matchers.query_param_matcher(
                {'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'S1_073251_IW2_20250413T020809_VV_EF1E-BURST'}
            )
        ],
        json={'items': []},
    )
    responses.get(
        url=prep_rtc.CMR_URL,
        match=[
            responses.matchers.query_param_matcher(
                {'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'foo_bad_burst_example_VV_-BURST'}
            )
        ],
        status=400,
    )

    responses.get(
        url=prep_rtc.CMR_URL,
        match=[
            responses.matchers.query_param_matcher(
                {'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'S1_146160_IW1_20241029T095958_VV_592B-BURST'}
            )
        ],
        json={'items': ['foo']},
    )
    responses.get(
        url=prep_rtc.CMR_URL,
        match=[
            responses.matchers.query_param_matcher(
                {'short_name': 'SENTINEL-1_BURSTS', 'granule_ur': 'S1_152193_IW3_20250415T143714_HH_EF65-BURST'}
            )
        ],
        json={'items': ['foo']},
    )

    assert prep_rtc.get_burst_from_cmr('S1_146160_IW1_20241029T095958_VV_592B-BURST')['items']
    assert prep_rtc.get_burst_from_cmr('S1_152193_IW3_20250415T143714_HH_EF65-BURST')['items']

    with pytest.raises(requests.HTTPError):
        prep_rtc.get_burst_from_cmr('foo_bad_burst_example_VV_-BURST')

    with pytest.raises(
        ValueError, match=r'^S1_073251_IW2_20250413T020809_VH_EF1E-BURST has polarization VH, must be VV or HH'
    ):
        prep_rtc.get_burst_from_cmr('S1_073251_IW2_20250413T020809_VH_EF1E-BURST')

    with pytest.raises(
        ValueError, match=r'^S1_241258_IW1_20250418T105137_HV_57A0-BURST has polarization HV, must be VV or HH'
    ):
        prep_rtc.get_burst_from_cmr('S1_241258_IW1_20250418T105137_HV_57A0-BURST')

    with pytest.raises(ValueError, match=r'^Granule does not exist: S1_073251_IW2_20250413T020809_VV_EF1E-BURST$'):
        prep_rtc.get_burst_from_cmr('S1_073251_IW2_20250413T020809_VV_EF1E-BURST')


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


@pytest.mark.skip
def test_get_granule_params():
    prep_rtc.get_burst_params('S1_146160_IW1_20241029T095958_VV_592B-BURST')
    prep_rtc.validate_slc('S1A_IW_SLC__1SDV_20250704T124517_20250704T124544_059934_0771EA_C208')
