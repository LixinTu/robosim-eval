#!/usr/bin/env bash
# run_batch.sh - RoboSim Eval D4: repeated runs of the preset scenarios with a reset before each, then the HTML report.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh [--scenarios a,b,c] [--repeats 3] [--out <dir>]
# Defaults: normal, bypass and unreachable, 3 repeats each (9 attempts), output artifacts/d4/batch-<time>/ with runs/,
# batch.json, runs/report.html and runs/summary.json.
# Ctrl-C in this terminal reaches the batch and the running attempt once each (timeout --foreground keeps them in the
# terminal's foreground process group): the attempt cancels its goal and closes out, then the batch stops (exit 20).
# Hard cap 4 h: the batch alone gets SIGTERM, lets the current attempt run to its own end, writes batch.json and the
# report and exits 20 (batch.json: stopped_by SIGTERM), or 31 when that attempt did not confirm its stop. Only if the
# batch is still running 1 h after the cap or after a Ctrl-C (far beyond one attempt) is it killed (exit 137;
# batch.json then still says "running"; the attempt in progress is not killed and finishes its own close-out).
# Exit: the batch's (0 all attempts ran; 31 aborted by an unconfirmed stop or a runner that did not close out;
#       20 interrupted or capped; 2 usage/config error; 30 report not written); 2 when the environment scripts failed;
#       137 killed 1 h after the cap or a Ctrl-C.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # the checkout this script is in
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
cd "$REPO" || exit 2
PYTHONDONTWRITEBYTECODE=1 timeout --foreground --preserve-status -s TERM -k 3600 14400 python3 -m robosim_eval.batch "$@"
