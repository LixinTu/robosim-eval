#!/usr/bin/env bash
# stop_nav2.sh — RoboSim Eval D0d: stop the launch started by start_nav2.sh and record how it ended (plan doc A7).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh <run_dir>
# 1. SIGINT to the `ros2 launch` process only; launch forwards it to its children. (Signalling the whole process group
#    delivers SIGINT twice to every child, which interrupted Nav2's own shutdown on 2026-09-29: SIGSEGV in cleanup.)
# 2. Wait up to 45 s for the whole session to exit; escalate to SIGTERM, then SIGKILL for the session only.
# 3. Read the launch's real exit code from nav2.exit (written by the wrapper), check leftover processes in the session
#    and leftover Nav2 nodes with a fresh discovery (--no-daemon; the ros2 daemon cache lists dead nodes for a while).
# Only the session recorded in <run_dir>/nav2.pid is signalled (plan doc B0: stop only what you own).
set -uo pipefail
RUN_DIR="${1:?run dir required}"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
[[ -f "$RUN_DIR/nav2.pid" ]] || { echo "no nav2.pid in $RUN_DIR"; exit 1; }
WRAP=$(cat "$RUN_DIR/nav2.pid")
alive() { pgrep -s "$WRAP" >/dev/null 2>&1; }
if ! alive; then
  echo "session $WRAP has no processes (already exited); exit code file: $(cat "$RUN_DIR/nav2.exit" 2>/dev/null || echo missing)"
  echo "stop_wall=$(date -Is) method=already-exited launch_exit=$(cat "$RUN_DIR/nav2.exit" 2>/dev/null || echo unknown)" >> "$RUN_DIR/nav2-launch.meta"
  exit 0
fi
# The launch is the wrapper's direct child. (Matching `-s <session> -f "ros2 launch ..."` also matches the wrapper bash,
# whose own command line contains that string; the wrapper traps INT, so the launch would never be told to stop.)
LAUNCH=$(pgrep -P "$WRAP" -f "ros2 launch" | head -1)
[[ -n "$LAUNCH" ]] || LAUNCH=$(sed -n 's/.*launch_pid=\([0-9]*\).*/\1/p' "$RUN_DIR/nav2-launch.meta" | tail -1)
T0=$(date +%s)
METHOD=""
if [[ -n "$LAUNCH" ]]; then
  echo "SIGINT -> ros2 launch pid $LAUNCH (session $WRAP) at $(date -Is)"; kill -INT "$LAUNCH"; METHOD="SIGINT(launch)"
else
  echo "no ros2 launch process found in session $WRAP; SIGINT -> whole session"; pkill -INT -s "$WRAP"; METHOD="SIGINT(session)"
fi
for _ in $(seq 1 45); do alive || break; sleep 1; done
if alive; then echo "still running after 45 s: SIGTERM -> session"; pkill -TERM -s "$WRAP"; METHOD="$METHOD+SIGTERM"; for _ in $(seq 1 10); do alive || break; sleep 1; done; fi
if alive; then echo "still running: SIGKILL -> session"; pkill -KILL -s "$WRAP"; METHOD="$METHOD+SIGKILL"; sleep 2; fi
ELAPSED=$(( $(date +%s) - T0 ))
LEFT_PROCS=$(pgrep -a -s "$WRAP" || true)
LEFT_NODES=$(timeout 20 ros2 node list --no-daemon --spin-time 3 2>/dev/null | grep -E '^/(lifecycle_manager|bt_navigator|controller_server|planner_server|amcl|map_server|rviz|collision_monitor|velocity_smoother|behavior_server|smoother_server|waypoint_follower|docking_server|route_server|pointcloud_to_laserscan)' || true)
RC=$(cat "$RUN_DIR/nav2.exit" 2>/dev/null || echo unknown)
echo "stopped in ${ELAPSED}s via $METHOD; launch exit code: $RC"
[[ -n "$LEFT_PROCS" ]] && { echo "WARNING: leftover processes in session $WRAP:"; echo "$LEFT_PROCS"; } || echo "no leftover processes in session $WRAP"
[[ -n "$LEFT_NODES" ]] && { echo "WARNING: Nav2 nodes still discovered (fresh discovery):"; echo "$LEFT_NODES"; } || echo "no Nav2 nodes discovered (fresh discovery, no daemon)"
echo "stop_wall=$(date -Is) method=$METHOD elapsed_s=$ELAPSED launch_exit=$RC leftover_procs=$([[ -n "$LEFT_PROCS" ]] && echo yes || echo no) leftover_nodes=$([[ -n "$LEFT_NODES" ]] && echo yes || echo no)" >> "$RUN_DIR/nav2-launch.meta"
EXITS_RE='process has finished|process has died|exited with|SIGSEGV|Segmentation'
if grep -qE "$EXITS_RE" "$RUN_DIR/nav2-launch.log"; then
  echo "process exits reported by launch:"; grep -E "$EXITS_RE" "$RUN_DIR/nav2-launch.log" | tail -n 12
else
  echo "launch log reports no child process exits (e.g. killed before it could log them)"
fi
# Exit status reflects the stop result only: 0 = nothing left behind, 1 = leftover processes or Nav2 nodes.
[[ -z "$LEFT_PROCS" && -z "$LEFT_NODES" ]]
