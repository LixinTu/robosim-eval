#!/usr/bin/env bash
# test_rviz.sh — RoboSim Eval D0b: can rviz2 start and stay up under WSLg? (plan doc C: "RViz 打不开")
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_rviz.sh [<out_dir>]
# Runs `timeout 20 rviz2` (exit 124 = it survived the whole window = PASS). On any other exit code it retries once
# with software OpenGL (LIBGL_ALWAYS_SOFTWARE=1) and the xcb Qt platform, and records both attempts.
set -uo pipefail
OUT="${1:-/mnt/d/RoboSim-Eval/artifacts/d0b}"
mkdir -p "$OUT"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only || exit 2
set -u
echo "=== test_rviz.sh $(date -Is) DISPLAY=${DISPLAY:-unset} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset} ==="

attempt() {  # attempt <name> [env assignments...]
  local name="$1"; shift
  local log="$OUT/rviz-$name.log"
  echo "--- attempt '$name' env: $* ---"
  env "$@" timeout 20 rviz2 > "$log" 2>&1
  local rc=$?
  echo "rviz2 exit=$rc (124 = survived 20 s) -> $log"
  echo "last lines:"; tail -n 6 "$log" | sed 's/^/    /'
  return $rc
}

attempt default; rc=$?
if [[ $rc -eq 124 ]]; then echo "=== result: PASS (default GL) ==="; exit 0; fi
attempt software LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb; rc=$?
if [[ $rc -eq 124 ]]; then echo "=== result: PASS (software GL: LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb) ==="; exit 0; fi
echo "=== result: FAIL (rviz2 exits early in both modes) ==="; exit 1
