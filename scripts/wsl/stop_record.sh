#!/usr/bin/env bash
# stop_record.sh — RoboSim Eval D0d: stop the recorders started by record_d0.sh, write `ros2 bag info`, copy the bag into
# <attempt_dir>/rosbag (git-ignored) and summarize what was captured, including each recorder's real exit code.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_record.sh <attempt_dir>
# Each recorder was started with setsid, so its recorded id is a session id; `timeout` creates its own process group
# inside that session, therefore the whole SESSION is signalled (pkill -s), not just one process group.
set -uo pipefail
ATT="${1:?attempt dir required}"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh || exit 2
set -u
[[ -f "$ATT/record.pids" ]] || { echo "no record.pids in $ATT"; exit 1; }
while read -r name sid; do
  [[ -n "${sid:-}" ]] || continue
  if pgrep -s "$sid" >/dev/null 2>&1; then pkill -INT -s "$sid"; echo "SIGINT -> session $name ($sid)"; else echo "$name ($sid) already exited"; fi
done < "$ATT/record.pids"
for _ in $(seq 1 20); do
  alive=0
  while read -r name sid; do [[ -n "${sid:-}" ]] && pgrep -s "$sid" >/dev/null 2>&1 && alive=1; done < "$ATT/record.pids"
  [[ $alive -eq 0 ]] && break; sleep 1
done
while read -r name sid; do
  [[ -n "${sid:-}" ]] || continue
  if pgrep -s "$sid" >/dev/null 2>&1; then echo "WARNING: session $name ($sid) still alive after 20 s; sending SIGTERM"; pkill -TERM -s "$sid"; fi
done < "$ATT/record.pids"
sleep 1
echo "record stop $(date -Is)" >> "$ATT/record.meta"
echo "recorder exit codes (124 = time cap reached; other values come from the recorder after SIGINT):"
while read -r name sid; do
  printf '  %-14s session %-7s exit=%s\n' "$name" "$sid" "$(cat "$ATT/$name.exit" 2>/dev/null || echo missing)"
done < "$ATT/record.pids" | tee -a "$ATT/record.meta"
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
