#!/usr/bin/env bash
# stop_nav2.sh — RoboSim Eval D0d: stop the launch started by start_nav2.sh and record how it ended (plan doc A7).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh <run_dir>
# 0. Ownership (plan doc B0: stop only what you have confirmed you own): the session in nav2.pid is signalled only if
#    the boot_id matches what start_nav2.sh recorded in nav2-launch.meta and either the wrapper still exists with the
#    recorded start time, a command line containing <run_dir>/nav2.exit and the ownership token (ROBOSIM_OWNER_TOKEN,
#    inherited by every process of the launch), or - the wrapper has exited, e.g. after `ros2 launch` itself died -
#    every process left in the session carries the token and started after the wrapper (findings shell-5, codex-b-6).
#    Run dirs are kept, and PIDs are reused after a WSL restart; anything unproven is refused (exit 5).
# 1. SIGINT to the `ros2 launch` process only; launch forwards it to its children. (Signalling the whole process group
#    delivers SIGINT twice to every child, which interrupted Nav2's own shutdown on 2026-09-29.) Without a launch
#    process (leftovers), SIGINT goes to the session.
# 2. Wait up to 45 s for the whole session to exit; escalate to SIGTERM for this session, then SIGKILL for every process
#    of the session except the wrapper, which then records the launch's real exit status (finding codex-b-8); only if
#    the wrapper itself is still there 5 s later is it killed as well.
# 3. Read the launch's real exit code from nav2.exit (written by the wrapper), check leftover processes in the session
#    and leftover Nav2 nodes with a fresh discovery (--no-daemon; the ros2 daemon cache lists dead nodes for a while).
# Exit: 0 nothing left behind and the launch's exit code recorded; 1 leftover processes or Nav2 nodes; 3 a leftover
#       check could not run (session query or node list failed: unknown); 4 nothing left behind, but the launch's exit
#       code was not recorded (nav2.exit missing or not a number); 5 refused: the session cannot be confirmed as this
#       run's launch.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
RUN_DIR="${1:?run dir required}"
[[ -d "$RUN_DIR" ]] || { echo "no run dir $RUN_DIR"; exit 1; }
RUN_DIR="$(cd "$RUN_DIR" && pwd -P)"   # the spelling start_nav2.sh used in the wrapper's command line
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
PROC="${ROBOSIM_PROC_ROOT:-/proc}"   # test seam: tests/shell point this at a fake /proc tree
META="$RUN_DIR/nav2-launch.meta"
[[ -f "$RUN_DIR/nav2.pid" ]] || { echo "no nav2.pid in $RUN_DIR"; exit 1; }
WRAP=$(cat "$RUN_DIR/nav2.pid")
[[ "$WRAP" =~ ^[0-9]+$ ]] || { echo "REFUSING: nav2.pid holds '$WRAP', not a process id"; exit 5; }
alive() { pgrep -s "$WRAP" >/dev/null 2>&1; [[ $? -ne 1 ]]; }   # a failed query counts as alive
stat_field() { sed -E 's/^.*\) //' "$PROC/$1/stat" 2>/dev/null | awk -v f="$2" '{print $f}'; }   # 4 session, 20 start
meta_value() { sed -n -E "s/^(.* )?$1=([^ ]*).*/\2/p" "$META" 2>/dev/null | tail -1; }
has_token() { [[ -n "$TOKEN" ]] && tr '\0' '\n' < "$PROC/$1/environ" 2>/dev/null | grep -qxF "ROBOSIM_OWNER_TOKEN=$TOKEN"; }
launch_exit() { local v; v=$(tr -d '[:space:]' < "$RUN_DIR/nav2.exit" 2>/dev/null); if [[ "$v" =~ ^[0-9]+$ ]]; then echo "$v"; else echo unknown; fi; }
TOKEN=$(meta_value token)

pgrep -s "$WRAP" >/dev/null 2>&1; Q=$?
if [[ $Q -gt 1 ]]; then
  echo "cannot query session $WRAP (pgrep exit $Q); nothing signalled, leftovers unknown"
  echo "stop_wall=$(date -Is) method=query-failed pgrep_exit=$Q" >> "$META"
  exit 3
fi
if [[ $Q -eq 1 ]]; then
  RC=$(launch_exit)
  echo "session $WRAP has no processes (already exited); launch exit code: $RC"
  echo "stop_wall=$(date -Is) method=already-exited launch_exit=$RC" >> "$META"
  if [[ $RC == unknown ]]; then echo "WARNING: the launch's exit code was not recorded (nav2.exit missing or not a number)"; exit 4; fi
  exit 0
fi

WHY=""; MODE=wrapper
if [[ "$(cat "$PROC/sys/kernel/random/boot_id" 2>/dev/null)" != "$(meta_value boot_id)" ]]; then
  WHY="boot_id differs from the one recorded at start (WSL restarted?)"
elif [[ -d "$PROC/$WRAP" ]]; then
  if [[ "$(stat_field "$WRAP" 20)" != "$(meta_value wrapper_starttime)" ]]; then
    WHY="start time of process $WRAP differs from the recorded wrapper start time"
  elif ! tr '\0' ' ' < "$PROC/$WRAP/cmdline" 2>/dev/null | grep -qF "$RUN_DIR/nav2.exit"; then
    WHY="process $WRAP is not this run dir's wrapper (command line does not reference $RUN_DIR/nav2.exit)"
  elif [[ -n "$TOKEN" ]] && ! has_token "$WRAP"; then
    WHY="process $WRAP does not carry this launch's ownership token"
  fi
else
  MODE=leftovers
  mapfile -t LEFT < <(pgrep -s "$WRAP")
  if [[ -z "$TOKEN" ]]; then
    WHY="wrapper $WRAP exited and ${#LEFT[@]} process(es) remain in its session (${LEFT[*]}); nav2-launch.meta has no ownership token (older start_nav2.sh), so they cannot be confirmed as this launch's"
  else
    for p in "${LEFT[@]}"; do
      if ! has_token "$p" || [[ "$(stat_field "$p" 20)" -lt "$(meta_value wrapper_starttime)" ]]; then
        WHY="wrapper $WRAP exited and process $p left in its session is not confirmed as this launch's (ownership token or start time)"; break
      fi
    done
  fi
fi
if [[ -n "$WHY" ]]; then
  echo "REFUSING to signal session $WRAP: $WHY"
  echo "stop_wall=$(date -Is) method=refused reason=\"$WHY\"" >> "$META"
  exit 5
fi
if [[ $MODE == leftovers ]]; then
  echo "wrapper $WRAP exited (launch exit code $(launch_exit)); ${#LEFT[@]} leftover process(es) of this launch remain in its session: ${LEFT[*]}"
fi

# The launch is the wrapper's direct child. (Matching `-s <session> -f "ros2 launch ..."` also matches the wrapper bash,
# whose own command line contains that string; the wrapper traps INT, so the launch would never be told to stop.)
LAUNCH=""
[[ $MODE == wrapper ]] && LAUNCH=$(pgrep -P "$WRAP" -f "ros2 launch" | head -1)
if [[ -z "$LAUNCH" ]]; then
  CAND=$(meta_value launch_pid)
  if [[ -n "$CAND" && -d "$PROC/$CAND" && "$(stat_field "$CAND" 4)" == "$WRAP" ]]; then LAUNCH=$CAND; fi
fi
T0=$(date +%s)
# `env kill` runs the external kill(1), not the builtin, so tests/shell can replace it with a stub on PATH.
if [[ -n "$LAUNCH" ]]; then
  echo "SIGINT -> ros2 launch pid $LAUNCH (session $WRAP) at $(date -Is)"; env kill -INT "$LAUNCH"; METHOD="SIGINT(launch)"
else
  echo "no ros2 launch process found in session $WRAP; SIGINT -> whole session"; pkill -INT -s "$WRAP"; METHOD="SIGINT(session)"
fi
for _ in $(seq 1 45); do alive || break; sleep 1; done
if alive; then echo "still running after 45 s: SIGTERM -> session"; pkill -TERM -s "$WRAP"; METHOD="$METHOD+SIGTERM"; for _ in $(seq 1 10); do alive || break; sleep 1; done; fi
if alive; then
  mapfile -t VICTIMS < <(pgrep -s "$WRAP" | grep -vx "$WRAP")
  echo "still running: SIGKILL -> every process of session $WRAP except the wrapper (${VICTIMS[*]}), so it can record the launch's exit status"
  [[ ${#VICTIMS[@]} -gt 0 ]] && env kill -KILL "${VICTIMS[@]}"
  METHOD="$METHOD+SIGKILL"
  for _ in $(seq 1 5); do alive || break; sleep 1; done
  if alive; then echo "wrapper still running 5 s later: SIGKILL -> whole session"; pkill -KILL -s "$WRAP"; METHOD="$METHOD+SIGKILL(wrapper)"; sleep 2; fi
fi
ELAPSED=$(( $(date +%s) - T0 ))
LEFT_PROCS=$(pgrep -a -s "$WRAP"); LQ=$?
NODES=$(timeout 20 ros2 node list --no-daemon --spin-time 3 2>&1); NRC=$?
if [[ $NRC -ne 0 ]]; then
  NODE_STATE=unknown; LEFT_NODES=""
else
  LEFT_NODES=$(grep -E '^/(lifecycle_manager|bt_navigator|controller_server|planner_server|amcl|map_server|rviz|collision_monitor|velocity_smoother|behavior_server|smoother_server|waypoint_follower|docking_server|route_server|pointcloud_to_laserscan)' <<<"$NODES")
  if [[ -n "$LEFT_NODES" ]]; then NODE_STATE=yes; else NODE_STATE=no; fi
fi
RC=$(launch_exit)
echo "stopped in ${ELAPSED}s via $METHOD; launch exit code: $RC"
if [[ $LQ -gt 1 ]]; then echo "WARNING: leftover-process check failed (pgrep exit $LQ); leftover processes unknown"; PROC_STATE=unknown
elif [[ -n "$LEFT_PROCS" ]]; then echo "WARNING: leftover processes in session $WRAP:"; echo "$LEFT_PROCS"; PROC_STATE=yes
else echo "no leftover processes in session $WRAP"; PROC_STATE=no; fi
case "$NODE_STATE" in
  yes) echo "WARNING: Nav2 nodes still discovered (fresh discovery):"; echo "$LEFT_NODES" ;;
  no) echo "no Nav2 nodes discovered (fresh discovery, no daemon)" ;;
  unknown) echo "WARNING: leftover-node check failed (ros2 node list exit $NRC); leftover nodes unknown"; echo "$NODES" | tail -5 ;;
esac
echo "stop_wall=$(date -Is) method=$METHOD elapsed_s=$ELAPSED launch_exit=$RC leftover_procs=$PROC_STATE leftover_nodes=$NODE_STATE" >> "$META"
EXITS_RE='process has finished|process has died|exited with|SIGSEGV|Segmentation'
if grep -qE "$EXITS_RE" "$RUN_DIR/nav2-launch.log"; then
  echo "process exits reported by launch:"; grep -E "$EXITS_RE" "$RUN_DIR/nav2-launch.log" | tail -n 12
else
  echo "launch log reports no child process exits (e.g. killed before it could log them)"
fi
if [[ "$PROC_STATE" == yes || "$NODE_STATE" == yes ]]; then exit 1; fi
if [[ "$PROC_STATE" == unknown || "$NODE_STATE" == unknown ]]; then exit 3; fi
if [[ "$RC" == unknown ]]; then echo "WARNING: the launch's exit code was not recorded (nav2.exit missing or not a number)"; exit 4; fi
exit 0
