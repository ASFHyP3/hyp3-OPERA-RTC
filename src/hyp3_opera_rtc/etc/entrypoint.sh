#!/bin/bash --login
set -e

# Make the PGE "opera" package discoverable because it is not installed
export PYTHONPATH=$PYTHONPATH:${PGE_DEST_DIR}

python -um hyp3_opera_rtc ++process prep_rtc "$@" --work-dir scratch
conda run -n RTC /home/rtc_user/opera/scripts/pge_main.py -f /home/rtc_user/scratch/runconfig.yml
python -um hyp3_opera_rtc ++process upload_rtc "$@" --work-dir scratch/output
