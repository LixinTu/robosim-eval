#!/usr/bin/env bash
# Wrapper: ROS environment + DDS profile (domain 0, the real Isaac), then rotation_response.py. Needs Nav2 stopped.
set -uo pipefail
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full >/dev/null || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh >/dev/null || exit 2
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONDONTWRITEBYTECODE=1 timeout -s INT 300 python3 "$HERE/rotation_response.py" "$@"
