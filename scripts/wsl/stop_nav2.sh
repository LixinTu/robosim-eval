#!/usr/bin/env bash
# stop_nav2.sh — RoboSim Eval D0d: stop the launch started by start_nav2.sh and record how it ended (plan doc A7).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh <run_dir>
# 0. Ownership (plan doc B0: stop only what you have confirmed you own): the session in nav2.pid is signalled only if
#    the boot_id, the wrapper's start time and its command line (containing <run_dir>/nav2.exit) match what start_nav2.sh
#    recorded in nav2-launch.meta. Run dirs are kept, and PIDs are reused after a WSL restart.
# 1. SIGINT to the `ros2 launch` process only; launch forwards it to its children. (Signalling the whole process group
#    delivers SIGINT twice to every child, which interrupted Nav2's own shutdown on 2026-09-29.)
# 2. Wait up to 45 s for the whole session to exit; escalate to SIGTERM, then SIGKILL for this session only.
# 3. Read the launch's real exit code from nav2.exit (written by the wrapper), check leftover processes in the session
#    and leftover Nav2 nodes with a fresh discovery (--no-daemon; the ros2 daemon cache lists dead nodes for a while).
# Exit: 0 nothing left behind; 1 leftover processes or Nav2 nodes; 3 leftover-node check could not run (unknown);
#       5 refused: the session cannot be confirmed as this run's launch.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
RUN_DIR="${1:?run dir required}"
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
META="$RUN_DIR/nav2-launch.meta"
[[ -f "$RUN_DIR/nav2.pid" ]] || { echo "no nav2.pid in $RUN_DIR"; exit 1; }
WRAP=$(cat "$RUN_DIR/nav2.pid")
alive() { pgrep -s "$WRAP" >/dev/null 2>&1; }
starttime_of() { sed -E 's/^.*\) //' "/proc/$1/stat" 2>/dev/null | awk '{print $20}'; }
meta_value() { sed -n "s/.*$1=\\([^ ]*\\).*/\\1/p" "$META" | tail -1; }

if ! alive; then
  echo "session $WRAP has no processes (already exited); exit code file: $(cat "$RUN_DIR/nav2.exit" 2>/dev/null || echo missing)"
  echo "stop_wall=$(date -Is) method=already-exited launch_exit=$(cat "$RUN_DIR/nav2.exit" 2>/dev/null || echo unknown)" >> "$META"
  exit 0
fi

WHY=""
[[ "$(cat /proc/sys/kernel/random/boot_id)" == "$(meta_value boot_id)" ]] || WHY="boot_id differs from the one recorded at start (WSL restarted?)"
[[ -z "$WHY" && "$(starttime_of "$WRAP")" != "$(meta_value wrapper_starttime)" ]] && WHY="start time of process $WRAP differs from the recorded wrapper start time"
[[ -z "$WHY" ]] && ! tr '\0' ' ' < "/proc/$WRAP/cmdline" 2>/dev/null | grep -qF "$RUN_DIR/nav2.exit" && WHY="process $WRAP is not this run dir's wrapper (command line does not reference $RUN_DIR/nav2.exit)"
if [[ -n "$WHY" ]]; then
  echo "REFUSING to signal session $WRAP: $WHY"
  echo "stop_wall=$(date -Is) method=refused reason=\"$WHY\"" >> "$META"
  exit 5
fi

# The launch is the wrapper's direct child. (Matching `-s <session> -f "ros2 launch ..."` also matches the wrapper bash,
# whose own command line contains that string; the wrapper traps INT, so the launch would never be told to stop.)
LAUNCH=$(pgrep -P "$WRAP" -f "ros2 launch" | head -1)
if [[ -z "$LAUNCH" ]]; then
  CAND=$(meta_value launch_pid)
  if [[ -n "$CAND" && "$(ps -o sid= -p "$CAND" 2>/dev/null | tr -d ' ')" == "$WRAP" ]]; then LAUNCH=$CAND; fi
fi
T0=$(date +%s)
if [[ -n "$LAUNCH" ]]; then
  echo "SIGINT -> ros2 launch pid $LAUNCH (session $WRAP) at $(date -Is)"; kill -INT "$LAUNCH"; METHOD="SIGINT(launch)"
else
  echo "no ros2 launch process found in session $WRAP; SIGINT -> whole session"; pkill -INT -s "$WRAP"; METHOD="SIGINT(session)"
fi
for _ in $(seq 1 45); do alive || break; sleep 1; done
if alive; then echo "still running after 45 s: SIGTERM -> session"; pkill -TERM -s "$WRAP"; METHOD="$METHOD+SIGTERM"; for _ in $(seq 1 10); do alive || break; sleep 1; done; fi
if alive; then echo "still running: SIGKILL -> session"; pkill -KILL -s "$WRAP"; METHOD="$METHOD+SIGKILL"; sleep 2; fi
ELAPSED=$(( $(date +%s) - T0 ))
LEFT_PROCS=$(pgrep -a -s "$WRAP")
NODES=$(timeout 20 ros2 node list --no-daemon --spin-time 3 2>&1); NRC=$?
if [[ $NRC -ne 0 ]]; then
  NODE_STATE=unknown; LEFT_NODES=""
else
  LEFT_NODES=$(grep -E '^/(lifecycle_manager|bt_navigator|controller_server|planner_server|amcl|map_server|rviz|collision_monitor|velocity_smoother|behavior_server|smoother_server|waypoint_follower|docking_server|route_server|pointcloud_to_laserscan)' <<<"$NODES")
  if [[ -n "$LEFT_NODES" ]]; then NODE_STATE=yes; else NODE_STATE=no; fi
fi
RC=$(cat "$RUN_DIR/nav2.exit" 2>/dev/null || echo unknown)
echo "stopped in ${ELAPSED}s via $METHOD; launch exit code: $RC"
if [[ -n "$LEFT_PROCS" ]]; then echo "WARNING: leftover processes in session $WRAP:"; echo "$LEFT_PROCS"; else echo "no leftover processes in session $WRAP"; fi
case "$NODE_STATE" in
  yes) echo "WARNING: Nav2 nodes still discovered (fresh discovery):"; echo "$LEFT_NODES" ;;
  no) echo "no Nav2 nodes discovered (fresh discovery, no daemon)" ;;
  unknown) echo "WARNING: leftover-node check failed (ros2 node list exit $NRC); leftover nodes unknown"; echo "$NODES" | tail -5 ;;
esac
echo "stop_wall=$(date -Is) method=$METHOD elapsed_s=$ELAPSED launch_exit=$RC leftover_procs=$([[ -n "$LEFT_PROCS" ]] && echo yes || echo no) leftover_nodes=$NODE_STATE" >> "$META"
EXITS_RE='process has finished|process has died|exited with|SIGSEGV|Segmentation'
if grep -qE "$EXITS_RE" "$RUN_DIR/nav2-launch.log"; then
  echo "process exits reported by launch:"; grep -E "$EXITS_RE" "$RUN_DIR/nav2-launch.log" | tail -n 12
else
  echo "launch log reports no child process exits (e.g. killed before it could log them)"
fi
if [[ -n "$LEFT_PROCS" || "$NODE_STATE" == yes ]]; then exit 1; fi
if [[ "$NODE_STATE" == unknown ]]; then exit 3; fi
exit 0
