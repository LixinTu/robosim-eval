#!/usr/bin/env bash
# record_d0.sh — RoboSim Eval D0d: record one navigation attempt's raw evidence (plan doc B6.5, A6).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh <attempt_dir> [<max_seconds>]
# Starts, detached and duration-capped (default 320 s wall, SIGINT so rosbag writes metadata.yaml):
#   - a rosbag (WSL-local ~/robosim_bags, copied into <attempt_dir>/rosbag afterwards; bags are git-ignored) with
#     /clock /chassis/odom /tf /tf_static /cmd_vel /scan /amcl_pose /plan /goal_pose /initialpose and the hidden
#     NavigateToPose action status/feedback topics
#   - wall-timestamped text streams: odom (csv), amcl_pose (csv), cmd_vel (csv), action status, tf map->base_link
# PIDs are written to <attempt_dir>/record.pids; stop early with stop_record.sh <attempt_dir>. Exit 0 when started.
set -uo pipefail
ATT="${1:?attempt dir required}"; MAX="${2:-320}"
mkdir -p "$ATT"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
BAG="$HOME/robosim_bags/$(basename "$ATT")-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$(dirname "$BAG")"
echo "$BAG" > "$ATT/bag-path.txt"
: > "$ATT/record.pids"

stamp() { python3 -u -c 'import sys,datetime
for line in sys.stdin: print(datetime.datetime.now().isoformat(timespec="milliseconds"), line.rstrip())'; }

start() { # start <name> <command...>   (detached, INT-capped)
  local name="$1"; shift
  setsid nohup bash -c 'echo $$ > "$0"; exec "$@"' "$ATT/pid-$name" timeout -s INT "$MAX" "$@" < /dev/null > "$ATT/$name.log" 2>&1 &
  sleep 0.5; echo "$name $(cat "$ATT/pid-$name" 2>/dev/null)" >> "$ATT/record.pids"
}
startpipe() { # startpipe <name> <command...>  (stdout wall-timestamped into <name>.txt)
  local name="$1"; shift
  setsid nohup bash -c 'echo $$ > "$0"; shift; exec "$@" | python3 -u -c "import sys,datetime
for line in sys.stdin: print(datetime.datetime.now().isoformat(timespec=\"milliseconds\"), line.rstrip())"' "$ATT/pid-$name" _ timeout -s INT "$MAX" "$@" < /dev/null > "$ATT/$name.txt" 2> "$ATT/$name.err" &
  sleep 0.5; echo "$name $(cat "$ATT/pid-$name" 2>/dev/null)" >> "$ATT/record.pids"
}

echo "record start $(date -Is) attempt=$ATT max=${MAX}s bag=$BAG" | tee "$ATT/record.meta"
start bag ros2 bag record -o "$BAG" --include-hidden-topics \
  /clock /chassis/odom /tf /tf_static /cmd_vel /scan /amcl_pose /plan /goal_pose /initialpose \
  /navigate_to_pose/_action/status /navigate_to_pose/_action/feedback
startpipe odom      ros2 topic echo --csv --field pose.pose /chassis/odom
startpipe amcl_pose ros2 topic echo --csv /amcl_pose
startpipe cmd_vel   ros2 topic echo --csv /cmd_vel
startpipe action_status ros2 topic echo /navigate_to_pose/_action/status
startpipe tf_map_base ros2 run tf2_ros tf2_echo map base_link -r 5
sleep 2
echo "pids:"; cat "$ATT/record.pids"
for p in $(awk '{print $2}' "$ATT/record.pids"); do kill -0 "$p" 2>/dev/null && echo "  running $p" || echo "  NOT running $p (see logs)"; done
