from pathlib import Path

import pytest

from hyp3_opera_rtc import prep_rtc


def test_render_runconfig(tmpdir):
    tmp_path = tmpdir / 'config.yml'

    args = {
        'config_path': tmp_path,
        'granule_name': 'granule.zip',
        'orbit_name': 'orbit.eof',
        'db_name': 'db.db',
        'dem_name': 'dem.tif',
        'config_type': 'pge',
        'resolution': 30,
        'container_base_path': Path('/foo/bar'),
    }
    prep_rtc.render_runconfig(**args)
    assert tmp_path.exists()
    with tmp_path.open() as file:
        contents = file.read()
        assert '/foo/bar/input/granule.zip' in contents
        assert '/foo/bar/input/orbit.eof' in contents
        assert '/foo/bar/input/db.db' in contents
        assert '/foo/bar/input/dem.tif' in contents
        assert '/foo/bar/scratch' in contents
        assert '/foo/bar/output' in contents
        assert 'x_posting: 30' in contents
        assert 'y_posting: 30' in contents
        assert 'PGE:' in contents

    args['config_type'] = 'sas'
    prep_rtc.render_runconfig(**args)
    with tmp_path.open() as file:
        contents = file.read()
        assert 'PGE:' not in contents

    args['config_type'] = 'foo'
    with pytest.raises(ValueError, match='Config type must be sas or pge.'):
        prep_rtc.render_runconfig(**args)
