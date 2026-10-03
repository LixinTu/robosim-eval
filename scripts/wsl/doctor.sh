#!/usr/bin/env bash
# doctor.sh - RoboSim Eval D1: bounded check of the ROS 2 environment, Isaac data and interfaces (plan doc A3/A4 D1).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor.sh [--out <dir>] [--window <s>] [--config <yaml>]
# Sources the ROS base environment and the Fast DDS profile, then runs `python3 -m robosim_eval.doctor` from the root of
# the checkout this script is in (a worktree runs its own doctor). Default config: configs/baseline.yaml. A hard 60 s
# cap guards against a hung doctor (exit 124 is reported as a failure, never as healthy).
# Exit: 0 healthy; 10 simulation not advancing (paused/stopped); 11 simulation data missing (closed, bridge not loaded,
#       DDS discovery broken, or a required topic without publisher); 12 degraded (slow, stale or silent stream);
#       13 environment or interface error, including a failed ROS or Fast DDS environment script; 2 usage/config error;
#       1 internal error; 124 hard cap hit.
# Set ROBOSIM_DOCTOR_DOMAIN to run against another ROS domain (used by the fake-node test; the config must match).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 2   # the checkout this script is in
env_failed() { echo "doctor.sh: $1 failed: the ROS 2 environment is not usable (environment error)" >&2; exit 13; }
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || env_failed ros_env.sh
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || env_failed dds_env.sh
set -u
if [[ -n "${ROBOSIM_DOCTOR_DOMAIN:-}" ]]; then export ROS_DOMAIN_ID="$ROBOSIM_DOCTOR_DOMAIN"; fi
cd "$REPO" || exit 2
PYTHONDONTWRITEBYTECODE=1 timeout 60 python3 -m robosim_eval.doctor --config "$REPO/configs/baseline.yaml" "$@"
rc=$?
if [[ $rc -eq 124 ]]; then echo "doctor.sh: hard 60 s cap hit (the doctor hung); treat as a failure" >&2; fi
exit $rc
