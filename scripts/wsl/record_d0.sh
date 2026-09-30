#!/usr/bin/env bash
# record_d0.sh — RoboSim Eval D0d: record one navigation attempt's raw evidence (plan doc B6.5, A6).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh <attempt_dir> [<max_seconds>]
# Starts, detached and duration-capped (default 320 s wall; timeout sends SIGINT so rosbag writes metadata.yaml):
#   - a rosbag (WSL-local ~/robosim_bags, copied into <attempt_dir>/rosbag afterwards; bags are git-ignored) with
#     /clock /chassis/odom /tf /tf_static /cmd_vel /scan /amcl_pose /plan /goal_pose /initialpose and the hidden
#     NavigateToPose action status/feedback topics
#   - wall-timestamped text streams: odom (csv), amcl_pose (csv), cmd_vel (csv), action status, tf map->base_link
# Each recorder runs in its own session (setsid) under a wrapper bash that writes the recorder's real exit code to
# <attempt_dir>/<name>.exit (124 = hit the time cap, by design; `ros2 topic echo` returns 2 = signal.SIGINT when stopped)
# and, for a text stream, the line stamper's exit code to <name>.stamp.exit (the whole PIPESTATUS is saved at once;
# finding codex-b-3). The wrapper survives a session-wide SIGINT/SIGTERM (SIGINT is ignored on entry for `&` jobs of a
# non-interactive shell; TERM is trapped) so it can record the exit codes; `timeout` installs its own signal handlers,
# so the recorders themselves get default dispositions and do stop on SIGINT (verified run-02).
# One recording per attempt dir (finding codex-b-4): record.pids is created exclusively (noclobber) before anything
# else is written, so a second record_d0.sh on the same dir - running or finished - is refused (exit 3).
# Ownership record for stop_record.sh (findings shell-3, codex-b-1): record.meta gets "owner boot_id=<id> token=<uuid>";
# the token is exported to every recorder process as ROBOSIM_OWNER_TOKEN; record.pids gets one line per recorder,
# "<name> <session id> <wrapper start time (/proc/<pid>/stat field 22)> <plain|pipe>", and each wrapper's command line
# names <attempt_dir>/<name>.exit. The session id is the launcher's pid ($!: setsid execs without forking in a shell
# without job control), confirmed by the pid file the wrapper writes (awaited up to 5 s); a wrapper whose pid file does
# not appear is still registered by that pid, so it can be stopped.
# When a recorder is not running 2 s after start or a pid file did not appear, everything started here is stopped with
# stop_record.sh before exit 1 (findings shell-4, codex-b-5): no recorder keeps writing into a failed attempt.
# Stop with stop_record.sh <attempt_dir>, which also checks that data arrived.
# Exit: 0 when every recorder is registered and running 2 s after start; 1 otherwise (see <name>.log / <name>.err);
#       2 environment; 3 refused: the attempt dir already has a recording (record.pids exists).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
ATT="${1:?attempt dir required}"; MAX="${2:-320}"
mkdir -p "$ATT" || exit 2
ATT="$(cd "$ATT" && pwd -P)"   # one spelling for the wrappers' command lines and stop_record.sh's check
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
PROC="${ROBOSIM_PROC_ROOT:-/proc}"   # test seam: tests/shell point this at a fake /proc tree
if ! ( set -o noclobber; : > "$ATT/record.pids" ) 2>/dev/null; then
  if [[ -e "$ATT/record.pids" ]]; then
    echo "ERROR: $ATT already has a recording (record.pids exists); use a new attempt dir"; exit 3
  fi
  echo "ERROR: cannot create $ATT/record.pids"; exit 2
fi
BOOT=$(cat "$PROC/sys/kernel/random/boot_id") || exit 2
TOKEN=$(cat /proc/sys/kernel/random/uuid) || exit 2
BAG="$HOME/robosim_bags/$(basename "$ATT")-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$(dirname "$BAG")"
echo "$BAG" > "$ATT/bag-path.txt"

# Line stamper for text streams: ignores SIGINT so it drains the pipe until EOF instead of dying with a traceback.
export STAMP_PY='import signal, sys, datetime
signal.signal(signal.SIGINT, signal.SIG_IGN)
for line in sys.stdin:
    print(datetime.datetime.now().isoformat(timespec="milliseconds"), line.rstrip(), flush=True)'

starttime_of() { sed -E 's/^.*\) //' "$PROC/$1/stat" 2>/dev/null | awk '{print $20}'; }
REG_FAIL=()
register() { # register <name> <launcher pid> <plain|pipe>: wait (up to 5 s) for the wrapper's pid file, then record it
  local name="$1" job="$2" kind="$3" sid="" st
  for _ in $(seq 1 25); do
    if [[ -s "$ATT/pid-$name" ]]; then sid=$(cat "$ATT/pid-$name"); break; fi
    sleep 0.2
  done
  if [[ -z "$sid" ]]; then sid="$job"; REG_FAIL+=("$name: no pid file after 5 s (registered by its launcher pid $job)"); fi
  st=$(starttime_of "$sid")
  echo "$name $sid ${st:--} $kind" >> "$ATT/record.pids"
}
start() { # start <name> <command...>   (detached, INT-capped, exit code -> <name>.exit)
  local name="$1"; shift
  rm -f "$ATT/$name.exit" "$ATT/pid-$name"
  ROBOSIM_OWNER_TOKEN="$TOKEN" setsid nohup bash -c 'echo $$ > "$0"; trap "true" INT TERM; "${@:2}"; echo $? > "$1"' \
    "$ATT/pid-$name" "$ATT/$name.exit" timeout -s INT "$MAX" "$@" < /dev/null > "$ATT/$name.log" 2>&1 &
  register "$name" "$!" plain
}
startpipe() { # startpipe <name> <command...>  (stdout wall-timestamped into <name>.txt; both exit codes kept)
  local name="$1"; shift
  rm -f "$ATT/$name.exit" "$ATT/$name.stamp.exit" "$ATT/pid-$name"
  ROBOSIM_OWNER_TOKEN="$TOKEN" setsid nohup bash -c 'echo $$ > "$0"; trap "true" INT TERM
"${@:3}" | python3 -u -c "$STAMP_PY"; st=("${PIPESTATUS[@]}"); echo "${st[1]}" > "$2"; echo "${st[0]}" > "$1"' \
    "$ATT/pid-$name" "$ATT/$name.exit" "$ATT/$name.stamp.exit" timeout -s INT "$MAX" "$@" < /dev/null > "$ATT/$name.txt" 2> "$ATT/$name.err" &
  register "$name" "$!" pipe
}

echo "record start $(date -Is) attempt=$ATT max=${MAX}s bag=$BAG" | tee "$ATT/record.meta"
echo "owner boot_id=$BOOT token=$TOKEN" >> "$ATT/record.meta"
start bag ros2 bag record -o "$BAG" --include-hidden-topics \
  /clock /chassis/odom /tf /tf_static /cmd_vel /scan /amcl_pose /plan /goal_pose /initialpose \
  /navigate_to_pose/_action/status /navigate_to_pose/_action/feedback
startpipe odom          ros2 topic echo --csv --field pose.pose /chassis/odom
startpipe amcl_pose     ros2 topic echo --csv /amcl_pose
startpipe cmd_vel       ros2 topic echo --csv /cmd_vel
startpipe action_status ros2 topic echo /navigate_to_pose/_action/status
startpipe tf_map_base   ros2 run tf2_ros tf2_echo map base_link -r 5
sleep 2
echo "sessions (name, session id, wrapper start time, kind):"; cat "$ATT/record.pids"
rc=0
while read -r name sid _; do
  if pgrep -s "$sid" >/dev/null 2>&1; then echo "  running $name (session $sid)"; else echo "  NOT running $name (session $sid; see $name.log/.err)"; rc=1; fi
done < "$ATT/record.pids"
for r in "${REG_FAIL[@]}"; do echo "  registration failed: $r"; rc=1; done
if [[ $rc -ne 0 ]]; then
  echo "record_d0: not every recorder started; stopping everything started here with stop_record.sh before exit 1"
  bash "$REPO/scripts/wsl/stop_record.sh" "$ATT"
  echo "record_d0: stop_record.sh exit $?"
fi
exit $rc
