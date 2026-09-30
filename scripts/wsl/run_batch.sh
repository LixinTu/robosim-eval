#!/usr/bin/env bash
# run_batch.sh - RoboSim Eval D4: repeated runs of the preset scenarios with a reset before each, then the HTML report.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh [--scenarios a,b,c] [--repeats 3] [--out <dir>]
# Defaults: normal, bypass and unreachable, 3 repeats each (9 attempts), output artifacts/d4/batch-<time>/ with runs/,
# batch.json, runs/report.html and runs/summary.json. Hard cap 4 h; on the cap the batch gets SIGINT and stops after the
# current attempt. Exit: 0 all attempts ran; 31 aborted by an unconfirmed stop; 20 interrupted; 2 usage/environment.
set -uo pipefail
REPO=/mnt/d/RoboSim-Eval
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
cd "$REPO" || exit 2
PYTHONDONTWRITEBYTECODE=1 timeout -s INT -k 1200 14400 python3 -m robosim_eval.batch "$@"
