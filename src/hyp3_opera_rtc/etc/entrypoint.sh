#!/bin/bash --login

# Taken from OPERA PGE entrypoint
DOCKER_ENTRYPOINT_SCRIPT_DIR=$(dirname ${BASH_SOURCE[0]})
PGE_PROGRAM_DIR=${PGE_DEST_DIR}
export PYTHONPATH=$PYTHONPATH:${PGE_PROGRAM_DIR}

exec python -um hyp3_opera_rtc "$@"
