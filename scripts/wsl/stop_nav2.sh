#!/usr/bin/env bash
# stop_nav2.sh — RoboSim Eval D0d: stop the launch started by start_nav2.sh (SIGINT to its process group, bounded
# wait, then verify no Nav2 nodes remain). Records stop time, method and exit code in <run_dir>/nav2-launch.meta.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh <run_dir>
# Only the process group recorded in <run_dir>/nav2.pid is signalled (plan doc B0: stop only what you own).
set -uo pipefail
RUN_DIR="${1:?run dir required}"
PIDFILE="$RUN_DIR/nav2.pid"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
if [[ ! -f "$PIDFILE" ]]; then echo "no pid file in $RUN_DIR"; exit 1; fi
PID=$(cat "$PIDFILE")
if ! kill -0 "$PID" 2>/dev/null; then
  echo "process $PID is not running (already exited)"; echo "stop_wall=$(date -Is) method=already-exited" >> "$RUN_DIR/nav2-launch.meta"; exit 0
fi
echo "sending SIGINT to process group $PID at $(date -Is)"
kill -INT -- "-$PID" 2>/dev/null || kill -INT "$PID"
for i in $(seq 1 30); do
  if ! kill -0 "$PID" 2>/dev/null; then break; fi
  sleep 1
done
if kill -0 "$PID" 2>/dev/null; then
  echo "still running after 30 s; sending SIGTERM to the group"
  kill -TERM -- "-$PID" 2>/dev/null || kill -TERM "$PID"
  sleep 5
fi
if kill -0 "$PID" 2>/dev/null; then METHOD="SIGINT+SIGTERM (still alive!)"; RC="unknown"; else METHOD="SIGINT (group)"; RC="exited"; fi
sleep 2
LEFT=$(timeout 15 ros2 node list 2>/dev/null | grep -E '^/(lifecycle_manager|bt_navigator|controller_server|planner_server|amcl|map_server|rviz)' || true)
if [[ -n "$LEFT" ]]; then echo "WARNING: leftover Nav2 nodes still visible:"; echo "$LEFT"; else echo "no leftover Nav2 nodes visible"; fi
echo "stop_wall=$(date -Is) method=$METHOD state=$RC leftovers=$( [[ -n "$LEFT" ]] && echo yes || echo no )" >> "$RUN_DIR/nav2-launch.meta"
echo "log tail:"; tail -n 5 "$RUN_DIR/nav2-launch.log"
