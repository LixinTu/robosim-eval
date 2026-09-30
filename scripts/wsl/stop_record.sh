#!/usr/bin/env bash
# stop_record.sh — RoboSim Eval D0d: stop the recorders started by record_d0.sh (SIGINT, bounded wait), write
# `ros2 bag info`, copy the bag into <attempt_dir>/rosbag (git-ignored) and summarize what was captured.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_record.sh <attempt_dir>
set -uo pipefail
ATT="${1:?attempt dir required}"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh || exit 2
set -u
[[ -f "$ATT/record.pids" ]] || { echo "no record.pids in $ATT"; exit 1; }
while read -r name pid; do
  [[ -n "${pid:-}" ]] || continue
  if kill -0 "$pid" 2>/dev/null; then kill -INT -- "-$pid" 2>/dev/null || kill -INT "$pid"; echo "INT -> $name ($pid)"; else echo "$name ($pid) already exited"; fi
done < "$ATT/record.pids"
for i in $(seq 1 20); do
  alive=0
  while read -r name pid; do [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null && alive=1; done < "$ATT/record.pids"
  [[ $alive -eq 0 ]] && break; sleep 1
done
echo "record stop $(date -Is)" >> "$ATT/record.meta"
BAG=$(cat "$ATT/bag-path.txt" 2>/dev/null || true)
if [[ -n "$BAG" && -d "$BAG" ]]; then
  ros2 bag info "$BAG" > "$ATT/bag-info.txt" 2>&1; echo "bag info exit=$?"
  mkdir -p "$ATT/rosbag" && cp -r "$BAG"/. "$ATT/rosbag/" && echo "bag copied to $ATT/rosbag ($(du -sh "$ATT/rosbag" | cut -f1))"
  grep -E 'Duration|Messages|Topic:' "$ATT/bag-info.txt" | head -20
else
  echo "no bag directory found ($BAG)"
fi
for f in odom amcl_pose cmd_vel action_status tf_map_base; do
  printf '%-14s %6d lines\n' "$f" "$(wc -l < "$ATT/$f.txt" 2>/dev/null || echo 0)"
done
