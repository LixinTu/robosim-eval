#!/usr/bin/env bash
# start_nav2.sh — RoboSim Eval D0d: launch carter_navigation (RViz + Nav2 bringup + pointcloud_to_laserscan) detached,
# with PID file, exit-code file and log, so the process outlives the calling wsl.exe invocation (plan doc B0/A7).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh [<run_dir>] [extra launch args...]
# Refuses to start when a carter_navigation launch or Nav2 nodes are already running, or when that cannot be checked
# (never two Nav2 instances, plan doc B6).
# Layout: a wrapper bash (new session via setsid; its PID = session id in nav2.pid) runs `ros2 launch` in the foreground
# and writes the launch's real exit code to nav2.exit when it ends. The wrapper traps INT/TERM (runs `true`), so a signal
# to the session never kills it before it has recorded the exit code; the trap is reset for the launch itself.
# Ownership record for stop_nav2.sh: boot_id, the wrapper's and the launch's start times (/proc/<pid>/stat field 22)
# and a fresh ownership token are written to nav2-launch.meta; the wrapper's command line contains this run dir's
# nav2.exit path, and the token is exported as ROBOSIM_OWNER_TOKEN to the wrapper, so every process of the launch
# inherits it and stop_nav2.sh can still prove leftovers of this launch after the wrapper has exited (shell-5).
# Map record for send_goal.sh and map_overview.sh (finding codex-b-7): the map this launch loads (the launch file's
# default, or the last map:= argument) is written to nav2-launch.meta as map_yaml= with the sha256 of its yaml and
# image, so goals are checked against the map Nav2 actually uses and a later change of the files is noticed.
# Exit: 0 started; 2 environment (including an unreadable map); 3 refused (already running or cannot check);
#       4 launch did not start.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
RUN_DIR="${1:-$REPO/artifacts/d0d/$(date +%Y%m%d-%H%M%S)}"
shift || true
mkdir -p "$RUN_DIR" || exit 2
RUN_DIR="$(cd "$RUN_DIR" && pwd -P)"   # one spelling for the wrapper's command line and stop_nav2.sh's check
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full || exit 2   # /opt/ros/jazzy + pinned overlay
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u

OVERLAY=$(ros2 pkg prefix carter_navigation) || { echo "ERROR: package carter_navigation not found (ros2 pkg prefix)"; exit 2; }
MAP="$OVERLAY/share/carter_navigation/maps/carter_warehouse_navigation.yaml"   # the launch file's default `map`
for a in "$@"; do if [[ "$a" == map:=* ]]; then MAP="${a#map:=}"; fi; done   # ros2 launch: the last map:= wins
[[ "$MAP" == /* ]] || MAP="$PWD/$MAP"
if [[ "$MAP" =~ [[:space:]] ]]; then echo "ERROR: map path contains whitespace (nav2-launch.meta is space-separated): $MAP"; exit 2; fi
MAP_ID=$(python3 - "$MAP" <<'PY'
import hashlib, os, sys
import yaml
path = sys.argv[1]
def sha(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()
try:
    with open(path) as f:
        image = os.path.join(os.path.dirname(path), yaml.safe_load(f)['image'])
    print(f"map_yaml={path} map_sha256={sha(path)} map_image={image} map_image_sha256={sha(image)}")
except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(1)
PY
) || { echo "ERROR: cannot read the map Nav2 would load ($MAP): $MAP_ID"; exit 2; }

PROC="${ROBOSIM_PROC_ROOT:-/proc}"   # test seam: tests/shell point this at a fake /proc tree
starttime_of() { sed -E 's/^.*\) //' "$PROC/$1/stat" 2>/dev/null | awk '{print $20}'; }

if [[ -f "$RUN_DIR/nav2.pid" ]] && pgrep -s "$(cat "$RUN_DIR/nav2.pid")" >/dev/null 2>&1; then
  echo "ERROR: session $(cat "$RUN_DIR/nav2.pid") from this run dir still has processes; stop it first"; exit 3
fi
if pgrep -f "ros2 launch carter_navigation" >/dev/null 2>&1; then
  echo "ERROR: a carter_navigation launch process is already running:"; pgrep -af "ros2 launch carter_navigation"; exit 3
fi
NODES=$(timeout 20 ros2 node list --no-daemon --spin-time 3 2>&1); NRC=$?
if [[ $NRC -ne 0 ]]; then
  echo "ERROR: cannot check for running Nav2 nodes (ros2 node list exit $NRC); refusing to start. Output:"; echo "$NODES"; exit 3
fi
if grep -qE '^/(lifecycle_manager_navigation|bt_navigator|controller_server|planner_server|amcl|map_server)$' <<<"$NODES"; then
  echo "ERROR: Nav2 nodes are already visible on this domain; refusing to start a second instance"; exit 3
fi

LOG="$RUN_DIR/nav2-launch.log"
rm -f "$RUN_DIR/nav2.exit" "$RUN_DIR/nav2.pid"
TOKEN=$(cat /proc/sys/kernel/random/uuid) || exit 2
{
  echo "start_wall=$(date -Is)"
  echo "cmd=ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true $*"
  echo "env RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION ROS_DOMAIN_ID=$ROS_DOMAIN_ID FASTRTPS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE DISPLAY=${DISPLAY:-unset}"
  echo "overlay=$OVERLAY"
  echo "$MAP_ID"
} > "$RUN_DIR/nav2-launch.meta"

# `env --default-signal=INT,TERM`: a non-interactive shell starts `&` jobs with SIGINT ignored, and that inherited
# SIG_IGN made `ros2 launch` ignore SIGINT entirely (2026-09-29 run-03). Restore the defaults before the wrapper starts.
ROBOSIM_OWNER_TOKEN="$TOKEN" setsid nohup env --default-signal=INT,TERM bash -c 'echo $$ > "$0"; trap "true" INT TERM; ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true "${@:2}"; echo $? > "$1"' \
  "$RUN_DIR/nav2.pid" "$RUN_DIR/nav2.exit" "$@" < /dev/null > "$LOG" 2>&1 &

WRAP=""; LAUNCH=""
for _ in $(seq 1 20); do                      # up to 10 s for the pid file and the launch child to appear
  sleep 0.5
  [[ -s "$RUN_DIR/nav2.pid" ]] || continue
  WRAP=$(cat "$RUN_DIR/nav2.pid")
  LAUNCH=$(pgrep -P "$WRAP" -f "ros2 launch" 2>/dev/null | head -1)
  [[ -n "$LAUNCH" ]] && break
done
if [[ -z "$WRAP" || -z "$LAUNCH" ]]; then
  echo "ERROR: launch did not start (wrapper=${WRAP:-none} launch=${LAUNCH:-none}); see $LOG"; tail -20 "$LOG"; exit 4
fi
echo "session=$WRAP launch_pid=$LAUNCH launch_starttime=$(starttime_of "$LAUNCH") boot_id=$(cat "$PROC/sys/kernel/random/boot_id") wrapper_starttime=$(starttime_of "$WRAP") token=$TOKEN" >> "$RUN_DIR/nav2-launch.meta"
echo "nav2 launch started: wrapper/session=$WRAP launch_pid=$LAUNCH run_dir=$RUN_DIR log=$LOG"
