#!/usr/bin/env bash
# start_nav2.sh — RoboSim Eval D0d: launch carter_navigation (RViz + Nav2 bringup + pointcloud_to_laserscan) detached,
# with PID file and timestamped log, so the process outlives the calling wsl.exe invocation (plan doc B0/A7).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh [<run_dir>] [extra launch args...]
# Refuses to start when Nav2 nodes are already visible (never two Nav2 instances, plan doc B6).
# Stop with scripts/wsl/stop_nav2.sh <run_dir> (SIGINT to the process group, bounded wait).
set -uo pipefail
RUN_DIR="${1:-/mnt/d/RoboSim-Eval/artifacts/d0d/$(date +%Y%m%d-%H%M%S)}"
shift || true
mkdir -p "$RUN_DIR"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh || exit 2          # full mode: /opt/ros/jazzy + pinned overlay
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u

if [[ -f "$RUN_DIR/nav2.pid" ]] && kill -0 "$(cat "$RUN_DIR/nav2.pid")" 2>/dev/null; then
  echo "ERROR: a launch from this run dir is still running (pid $(cat "$RUN_DIR/nav2.pid"))"; exit 3
fi
if timeout 15 ros2 node list 2>/dev/null | grep -qE '^/(lifecycle_manager|bt_navigator|controller_server|planner_server|amcl|map_server)'; then
  echo "ERROR: Nav2 nodes are already running on this domain; refusing to start a second instance"; exit 3
fi

LOG="$RUN_DIR/nav2-launch.log"
{
  echo "start_wall=$(date -Is)"
  echo "cmd=ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true $*"
  echo "env RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION ROS_DOMAIN_ID=$ROS_DOMAIN_ID FASTRTPS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE DISPLAY=${DISPLAY:-unset}"
  echo "overlay=$(ros2 pkg prefix carter_navigation)"
} > "$RUN_DIR/nav2-launch.meta"

# setsid: new session/process group so stop_nav2.sh can signal the whole tree; the child records its own PID.
setsid nohup bash -c 'echo $$ > "$0"; exec ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true "$@"' \
  "$RUN_DIR/nav2.pid" "$@" < /dev/null > "$LOG" 2>&1 &
sleep 2
PID=$(cat "$RUN_DIR/nav2.pid" 2>/dev/null || echo "?")
if [[ "$PID" == "?" ]] || ! kill -0 "$PID" 2>/dev/null; then
  echo "ERROR: launch did not start (see $LOG)"; tail -20 "$LOG"; exit 4
fi
echo "nav2 launch started pid=$PID run_dir=$RUN_DIR log=$LOG"
echo "pid=$PID" >> "$RUN_DIR/nav2-launch.meta"
