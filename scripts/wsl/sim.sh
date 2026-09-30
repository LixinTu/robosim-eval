#!/usr/bin/env bash
# sim.sh - RoboSim Eval D2: control Isaac Sim through isaacsim.ros2.sim_control (ROS 2 simulation_interfaces).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh <command> [args]
# Commands: state | play | pause | stop | load [<uri>] | reset | pose [<entity>] | reset-check
#           | spawn-box <name> <x> <y> [<yaw>] | delete <name>        (see robosim_eval/sim_adapter.py)
# Prints one JSON line. Exit: 0 ok; 3 service unavailable/timeout/error; 4 reset-check failed; 2 usage, config or
# environment error. Isaac must have been started by scripts/windows/start_isaac_ros2.ps1 (sim_control enabled).
set -uo pipefail
REPO=/mnt/d/RoboSim-Eval
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
cd "$REPO" || exit 2
PYTHONDONTWRITEBYTECODE=1 timeout 300 python3 -m robosim_eval.sim_adapter "$@"
