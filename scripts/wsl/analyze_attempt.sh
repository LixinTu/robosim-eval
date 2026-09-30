#!/usr/bin/env bash
# analyze_attempt.sh — RoboSim Eval D0d: run analyze_attempt.py inside the ROS environment (rosbag2_py, rclpy).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/analyze_attempt.sh <attempt_dir> --goal X Y YAW [options]
set -uo pipefail
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only || exit 2
set -u
exec python3 /mnt/d/RoboSim-Eval/scripts/wsl/analyze_attempt.py "$@"
