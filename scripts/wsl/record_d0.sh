#!/usr/bin/env bash
# record_d0.sh — RoboSim Eval D0d: record one navigation attempt's raw evidence (plan doc B6.5, A6).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh <attempt_dir> [<max_seconds>]
# Starts, detached and duration-capped (default 320 s wall; timeout sends SIGINT so rosbag writes metadata.yaml):
#   - a rosbag (WSL-local ~/robosim_bags, copied into <attempt_dir>/rosbag afterwards; bags are git-ignored) with
#     /clock /chassis/odom /tf /tf_static /cmd_vel /scan /amcl_pose /plan /goal_pose /initialpose and the hidden
#     NavigateToPose action status/feedback topics
#   - wall-timestamped text streams: odom (csv), amcl_pose (csv), cmd_vel (csv), action status, tf map->base_link
# Each recorder runs in its own session (setsid) under a wrapper bash that writes the recorder's real exit code to
# <attempt_dir>/<name>.exit (124 = hit the time cap, by design; `ros2 topic echo` returns 2 = signal.SIGINT when stopped).
# Session ids are in <attempt_dir>/record.pids; stale pid files are deleted first and each new session id is awaited
# (up to 5 s) instead of a fixed sleep. The wrapper survives a session-wide SIGINT/SIGTERM (SIGINT is ignored on entry
# for `&` jobs of a non-interactive shell; TERM is trapped) so it can record the exit code; `timeout` installs its own
# signal handlers, so the recorders themselves get default dispositions and do stop on SIGINT (verified run-02).
# Stop with stop_record.sh <attempt_dir>, which also checks that data arrived.
# Exit: 0 when every recorder is running 2 s after start; 1 otherwise (see <name>.log / <name>.err).
set -uo pipefail
ATT="${1:?attempt dir required}"; MAX="${2:-320}"
mkdir -p "$ATT"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
BAG="$HOME/robosim_bags/$(basename "$ATT")-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$(dirname "$BAG")"
echo "$BAG" > "$ATT/bag-path.txt"
: > "$ATT/record.pids"

# Line stamper for text streams: ignores SIGINT so it drains the pipe until EOF instead of dying with a traceback.
export STAMP_PY='import signal, sys, datetime
signal.signal(signal.SIGINT, signal.SIG_IGN)
for line in sys.stdin:
    print(datetime.datetime.now().isoformat(timespec="milliseconds"), line.rstrip(), flush=True)'

register() { # register <name>: wait (up to 5 s) for the wrapper to write its session id, then record it
  local name="$1" sid=""
  for _ in $(seq 1 25); do
    if [[ -s "$ATT/pid-$name" ]]; then sid=$(cat "$ATT/pid-$name"); break; fi
    sleep 0.2
  done
  echo "$name ${sid:-MISSING}" >> "$ATT/record.pids"
}
start() { # start <name> <command...>   (detached, INT-capped, exit code -> <name>.exit)
  local name="$1"; shift
  rm -f "$ATT/$name.exit" "$ATT/pid-$name"
  setsid nohup bash -c 'echo $$ > "$0"; trap "true" INT TERM; "${@:2}"; echo $? > "$1"' \
    "$ATT/pid-$name" "$ATT/$name.exit" timeout -s INT "$MAX" "$@" < /dev/null > "$ATT/$name.log" 2>&1 &
  register "$name"
}
startpipe() { # startpipe <name> <command...>  (stdout wall-timestamped into <name>.txt, exit code of the command)
  local name="$1"; shift
  rm -f "$ATT/$name.exit" "$ATT/pid-$name"
  setsid nohup bash -c 'echo $$ > "$0"; trap "true" INT TERM; "${@:2}" | python3 -u -c "$STAMP_PY"; echo "${PIPESTATUS[0]}" > "$1"' \
    "$ATT/pid-$name" "$ATT/$name.exit" timeout -s INT "$MAX" "$@" < /dev/null > "$ATT/$name.txt" 2> "$ATT/$name.err" &
  register "$name"
}

echo "record start $(date -Is) attempt=$ATT max=${MAX}s bag=$BAG" | tee "$ATT/record.meta"
start bag ros2 bag record -o "$BAG" --include-hidden-topics \
  /clock /chassis/odom /tf /tf_static /cmd_vel /scan /amcl_pose /plan /goal_pose /initialpose \
  /navigate_to_pose/_action/status /navigate_to_pose/_action/feedback
startpipe odom          ros2 topic echo --csv --field pose.pose /chassis/odom
startpipe amcl_pose     ros2 topic echo --csv /amcl_pose
startpipe cmd_vel       ros2 topic echo --csv /cmd_vel
startpipe action_status ros2 topic echo /navigate_to_pose/_action/status
startpipe tf_map_base   ros2 run tf2_ros tf2_echo map base_link -r 5
sleep 2
echo "sessions:"; cat "$ATT/record.pids"
rc=0
while read -r name sid; do
  if [[ "$sid" =~ ^[0-9]+$ ]] && pgrep -s "$sid" >/dev/null 2>&1; then echo "  running $name (session $sid)"; else echo "  NOT running $name (session $sid; see $name.log/.err)"; rc=1; fi
done < "$ATT/record.pids"
exit $rc
