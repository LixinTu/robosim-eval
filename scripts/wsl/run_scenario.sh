#!/usr/bin/env bash
# run_scenario.sh - RoboSim Eval D2: one config-driven A->B run on the real Isaac (robosim_eval.runner).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh <scenario> [--out <dir>] [--config <yaml>]
# Scenarios are defined in configs/baseline.yaml (normal, bypass, unreachable). The runner resets the scene through
# sim_control, starts and stops Nav2, records, sends the goal, confirms the stop and writes the run directory (A6).
# Hard cap: 1500 s wall; on the cap the runner gets SIGINT (it cancels, stops the robot and tears down) and is killed
# 120 s later only if it is still running.
# Exit: the runner's (0 pass, 10 fail, 11 inconclusive, 20 interrupted, 30 error, 31 error that aborts a batch,
#       2 usage/config); 124 when the hard cap fired; 2 when the environment scripts failed.
set -uo pipefail
REPO=/mnt/d/RoboSim-Eval
SCENARIO="${1:?scenario name}"; shift
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
cd "$REPO" || exit 2
PYTHONDONTWRITEBYTECODE=1 timeout -s INT -k 120 1500 python3 -m robosim_eval.runner --scenario "$SCENARIO" "$@"
