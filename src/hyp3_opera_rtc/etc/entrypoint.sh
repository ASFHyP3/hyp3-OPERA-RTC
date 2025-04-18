#!/bin/bash --login
set -e

# Make the PGE "opera" package discoverable because it is not installed
export PYTHONPATH=$PYTHONPATH:${PGE_DEST_DIR}

python -um hyp3_opera_rtc "$@" --work-dir scratch
