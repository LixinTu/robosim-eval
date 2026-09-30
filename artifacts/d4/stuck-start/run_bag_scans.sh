#!/usr/bin/env bash
# Offline scans over every real run directory under artifacts/ (no Isaac needed): the first /plan direction vs the
# AMCL heading and the first /cmd_vel (plan_heading.py, reads the rosbags kept on this machine), and the length of the
# minimum-rotation phase at the start of /cmd_vel (cmd_vel_scan.py, reads cmd_vel.txt).
set -uo pipefail
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full >/dev/null || exit 2
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
A=/mnt/d/RoboSim-Eval/artifacts
mapfile -t RUNS < <(ls -d "$A"/d2/runs/normal-* "$A"/d3/runs/*-2026* "$A"/d3/runs-diagnosis/*-2026* "$A"/d4/batch-*/runs/*-2026* \
  "$A"/d5/*/*-2026* 2>/dev/null | while read -r d; do [[ -d "$d/rosbag" ]] && echo "$d"; done)
python3 "$HERE/plan_heading.py" "${RUNS[@]}" 2>&1 | grep -v '^\[INFO\]'
echo "---"
python3 "$HERE/cmd_vel_scan.py"
