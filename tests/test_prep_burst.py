import unittest.mock

import pytest

from hyp3_opera_rtc import prep_burst


def test_get_cross_pol_name():
    assert (
        prep_burst.get_cross_pol_name('S1_073251_IW2_20250413T020809_VV_EF1E-BURST')
        == 'S1_073251_IW2_20250413T020809_VH_EF1E-BURST'
    )
    assert (
        prep_burst.get_cross_pol_name('S1_241258_IW1_20250418T105137_HH_57A0-BURST')
        == 'S1_241258_IW1_20250418T105137_HV_57A0-BURST'
    )
    with pytest.raises(
        ValueError, match=r'^S1_073251_IW2_20250413T020809_VH_EF1E-BURST has polarization VH, must be VV or HH$'
    ):
        prep_burst.get_cross_pol_name('S1_073251_IW2_20250413T020809_VH_EF1E-BURST')


def test_get_cross_pol_granules():
    def mock_granule_exists(granule: str) -> bool:
        return granule in [
            'S1_146160_IW1_20241029T095958_VV_592B-BURST',
            'S1_073251_IW2_20250413T020809_VV_EF1E-BURST',
            'S1_152193_IW3_20250415T143714_HH_EF65-BURST',
            'S1_241258_IW1_20250418T105137_HH_57A0-BURST',
            'S1_073251_IW2_20250413T020809_VH_EF1E-BURST',
            'S1_241258_IW1_20250418T105137_HV_57A0-BURST',
        ]

    with unittest.mock.patch('hyp3_opera_rtc.prep_burst.granule_exists', mock_granule_exists):
        assert prep_burst.get_cross_pol_granules(
            [
                'S1_146160_IW1_20241029T095958_VV_592B-BURST',
                'S1_073251_IW2_20250413T020809_VV_EF1E-BURST',
                'S1_152193_IW3_20250415T143714_HH_EF65-BURST',
                'S1_241258_IW1_20250418T105137_HH_57A0-BURST',
            ]
        ) == [
            'S1_073251_IW2_20250413T020809_VH_EF1E-BURST',
            'S1_241258_IW1_20250418T105137_HV_57A0-BURST',
        ]

        with pytest.raises(ValueError, match=r'^Granule does not exist: S1_371285_IW2_20230220T142909_HH_02D7-BURST$'):
            prep_burst.get_cross_pol_granules(['S1_371285_IW2_20230220T142909_HH_02D7-BURST'])

        with pytest.raises(
            ValueError, match=r'^S1_073251_IW2_20250413T020809_VH_EF1E-BURST has polarization VH, must be VV or HH$'
        ):
            prep_burst.get_cross_pol_granules(['S1_073251_IW2_20250413T020809_VH_EF1E-BURST'])
