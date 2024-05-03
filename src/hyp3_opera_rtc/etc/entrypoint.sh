#!/bin/bash --login
set -e
conda activate hyp3-opera-rtc
exec python -um hyp3_opera_rtc "$@"
