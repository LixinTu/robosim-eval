#!/usr/bin/env bash
# analyze_attempt.sh — RoboSim Eval D0d: run analyze_attempt.py inside the ROS environment (rosbag2_py, rclpy).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/analyze_attempt.sh <attempt_dir> --goal X Y YAW [options]
# Uses the checkout this script is in (the same files as before when run from /mnt/d/RoboSim-Eval).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
set -u
exec python3 "$REPO/scripts/wsl/analyze_attempt.py" "$@"
