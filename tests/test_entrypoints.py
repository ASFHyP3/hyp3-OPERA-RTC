def test_hyp3_opera_rtc(script_runner):
    ret = script_runner.run('python', '-m', 'hyp3_opera_rtc', '++process', 'opera_rtc', '-h')
    assert ret.success
