#!/bin/bash --login
set -e

# Make the PGE "opera" package discoverable because it is not installed
export PYTHONPATH=$PYTHONPATH:${PGE_DEST_DIR}

python -um hyp3_opera_rtc.prep_rtc "$@" --work-dir /home/rtc_user
conda run -n RTC /home/rtc_user/opera/scripts/pge_main.py -f /home/rtc_user/runconfig.yml
python -um hyp3_opera_rtc.upload_rtc "$@" --output-dir /home/rtc_user/output_dir
