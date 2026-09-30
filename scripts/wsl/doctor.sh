#!/usr/bin/env bash
# doctor.sh - RoboSim Eval D1: bounded check of the ROS 2 environment, Isaac data and interfaces (plan doc A3/A4 D1).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor.sh [--out <dir>] [--window <s>] [--config <yaml>]
# Sources the ROS base environment and the Fast DDS profile, then runs `python3 -m robosim_eval.doctor` from the repo
# root. Default config: configs/baseline.yaml. A hard 60 s cap guards against a hung doctor (exit 124 is reported as a
# failure, never as healthy).
# Exit: 0 healthy; 10 simulation not advancing (paused/stopped); 11 simulation data missing (closed, bridge not loaded,
#       DDS discovery broken, or a required topic without publisher); 12 degraded (slow, stale or silent stream);
#       13 environment or interface error; 2 usage/config error or environment scripts failed; 1 internal error;
#       124 hard cap hit.
# Set ROBOSIM_DOCTOR_DOMAIN to run against another ROS domain (used by the fake-node test; the config must match).
set -uo pipefail
REPO=/mnt/d/RoboSim-Eval
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
if [[ -n "${ROBOSIM_DOCTOR_DOMAIN:-}" ]]; then export ROS_DOMAIN_ID="$ROBOSIM_DOCTOR_DOMAIN"; fi
cd "$REPO" || exit 2
PYTHONDONTWRITEBYTECODE=1 timeout 60 python3 -m robosim_eval.doctor --config "$REPO/configs/baseline.yaml" "$@"
rc=$?
if [[ $rc -eq 124 ]]; then echo "doctor.sh: hard 60 s cap hit (the doctor hung); treat as a failure" >&2; fi
exit $rc
