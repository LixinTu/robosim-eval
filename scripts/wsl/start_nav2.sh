#!/usr/bin/env bash
# start_nav2.sh — RoboSim Eval D0d: launch carter_navigation (RViz + Nav2 bringup + pointcloud_to_laserscan) detached,
# with PID file, exit-code file and log, so the process outlives the calling wsl.exe invocation (plan doc B0/A7).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh [<run_dir>] [extra launch args...]
# Refuses to start when Nav2 nodes are already running (never two Nav2 instances, plan doc B6).
# Layout: a wrapper bash (new session via setsid; PID in nav2.pid) runs `ros2 launch` in the foreground and writes the
# launch's real exit code to nav2.exit when it ends. The wrapper traps INT/TERM (runs `true`), so a signal to the session
# never kills the wrapper before it has recorded the exit code; the trap is reset for the launch itself.
# Stop with scripts/wsl/stop_nav2.sh <run_dir>.
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

if [[ -f "$RUN_DIR/nav2.pid" ]] && pgrep -s "$(cat "$RUN_DIR/nav2.pid")" >/dev/null 2>&1; then
  echo "ERROR: a launch from this run dir is still running (session $(cat "$RUN_DIR/nav2.pid"))"; exit 3
fi
if pgrep -f "ros2 launch carter_navigation" >/dev/null 2>&1; then
  echo "ERROR: a carter_navigation launch process is already running:"; pgrep -af "ros2 launch carter_navigation"; exit 3
fi
if timeout 20 ros2 node list --no-daemon --spin-time 3 2>/dev/null | grep -qE '^/(lifecycle_manager_navigation|bt_navigator|controller_server|planner_server|amcl|map_server)$'; then
  echo "ERROR: Nav2 nodes are already visible on this domain; refusing to start a second instance"; exit 3
fi

LOG="$RUN_DIR/nav2-launch.log"
rm -f "$RUN_DIR/nav2.exit"
{
  echo "start_wall=$(date -Is)"
  echo "cmd=ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true $*"
  echo "env RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION ROS_DOMAIN_ID=$ROS_DOMAIN_ID FASTRTPS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE DISPLAY=${DISPLAY:-unset}"
  echo "overlay=$(ros2 pkg prefix carter_navigation)"
} > "$RUN_DIR/nav2-launch.meta"

# `env --default-signal=INT,TERM`: a non-interactive shell starts `&` jobs with SIGINT ignored, and that inherited
# SIG_IGN made `ros2 launch` ignore SIGINT entirely (2026-09-29 run-03). Restore the defaults before the wrapper starts.
setsid nohup env --default-signal=INT,TERM bash -c 'echo $$ > "$0"; trap "true" INT TERM; ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true "${@:2}"; echo $? > "$1"' \
  "$RUN_DIR/nav2.pid" "$RUN_DIR/nav2.exit" "$@" < /dev/null > "$LOG" 2>&1 &
sleep 3
WRAP=$(cat "$RUN_DIR/nav2.pid" 2>/dev/null || echo "?")
LAUNCH=$(pgrep -P "$WRAP" -f "ros2 launch" 2>/dev/null | head -1)
if [[ "$WRAP" == "?" || -z "$LAUNCH" ]]; then
  echo "ERROR: launch did not start (wrapper=$WRAP launch=${LAUNCH:-none}); see $LOG"; tail -20 "$LOG"; exit 4
fi
echo "nav2 launch started: wrapper/session=$WRAP launch_pid=$LAUNCH run_dir=$RUN_DIR log=$LOG"
echo "session=$WRAP launch_pid=$LAUNCH" >> "$RUN_DIR/nav2-launch.meta"
