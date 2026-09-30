#!/usr/bin/env bash
# run_scenario.sh - RoboSim Eval D2: one config-driven A->B run on the real Isaac (robosim_eval.runner).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh <scenario> [--out <dir>] [--config <yaml>]
# Scenarios are defined in configs/baseline.yaml (normal, bypass, unreachable). The runner resets the scene through
# sim_control, starts and stops Nav2, records, sends the goal, confirms the stop and writes the run directory (A6).
# Uses the checkout this script is in (the same files as before when run from /mnt/d/RoboSim-Eval).
# Ctrl-C in the terminal reaches the runner: it cancels the goal, confirms the stop and tears down (exit 20).
# Hard cap: 1500 s wall; on the cap the runner gets SIGINT (it cancels, stops the robot and tears down) and is killed
# 120 s later only if it is still running.
# ROBOSIM_RUN_DOMAIN (fake-node test only) replaces the ROS domain that ros_env.sh sets.
# Exit: the runner's (0 pass, 10 fail, 11 inconclusive, 20 interrupted, 30 error, 31 error that aborts a batch,
#       2 usage/config or another runner active); 124 when the hard cap fired; 2 when the environment scripts failed.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCENARIO="${1:?scenario name}"; shift
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
if [[ -n "${ROBOSIM_RUN_DOMAIN:-}" ]]; then export ROS_DOMAIN_ID="$ROBOSIM_RUN_DOMAIN"; fi
cd "$REPO" || exit 2
# --foreground keeps python in the terminal's foreground process group, so a terminal Ctrl-C reaches the runner.
# Without it timeout moves itself and python into a new background group and ^C only hits this non-interactive bash,
# which waits (the run went on to its normal end). What --foreground changes: the cap's INT and the KILL 120 s later go
# to the runner process only, not to a process group (the runner starts every script in its own session anyway, so
# those were never in the group); and timeout also forwards a terminal Ctrl-C and then arms the same 120 s KILL, so the
# teardown after a Ctrl-C has 120 s, as after the cap (it took 16-34 s in the recorded runs).
PYTHONDONTWRITEBYTECODE=1 timeout --foreground -s INT -k 120 1500 python3 -m robosim_eval.runner --scenario "$SCENARIO" "$@"
