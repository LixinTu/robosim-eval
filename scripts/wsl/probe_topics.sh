#!/usr/bin/env bash
# probe_topics.sh — RoboSim Eval D0c: what does WSL actually receive from Isaac Sim right now? (plan doc B5 table)
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_topics.sh [<out_dir>] [topic ...]
# Every observation is time-bounded. Records: node list, topic list with types, /clock rate, and for each candidate
# topic that exists: publisher/subscriber info with QoS (`ros2 topic info -v`), rate (`ros2 topic hz`, 8 s) and one
# sample (`ros2 topic echo --once --no-arr`). TF is read with tf2_echo (bounded). Nothing is published.
# Exit 0 when /clock is advancing; 1 otherwise (the raw evidence is written either way).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
OUT="${1:-$REPO/artifacts/d0c/$(date +%Y%m%d-%H%M%S)}"
shift || true
mkdir -p "$OUT"
CANDIDATES=("$@")
if [[ ${#CANDIDATES[@]} -eq 0 ]]; then
  CANDIDATES=(/clock /tf /tf_static /odom /chassis/odom /front_3d_lidar/lidar_points /point_cloud /front_2d_lidar/scan /back_2d_lidar/scan /scan /cmd_vel /joint_states /map)
fi

set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u

run() { local title="$1"; shift; echo; echo "===== $title ====="; echo "CMD: $*"; "$@"; echo "EXIT: $?"; }

{
echo "=== probe_topics.sh $(date -Is) out=$OUT RMW=$RMW_IMPLEMENTATION DOMAIN=$ROS_DOMAIN_ID profile=${FASTRTPS_DEFAULT_PROFILES_FILE:-unset} ==="
run "ros2 daemon (fresh discovery)" ros2 daemon stop
run "node list" timeout 15 ros2 node list
run "topic list -t" timeout 15 ros2 topic list -t
} | tee "$OUT/00-discovery.txt"

CLOCK_OK=0
{
run "/clock hz (10 s)" timeout 10 ros2 topic hz /clock --window 50
run "/clock sample" timeout 10 ros2 topic echo --once /clock
} | tee "$OUT/01-clock.txt"
if grep -q 'average rate' "$OUT/01-clock.txt"; then CLOCK_OK=1; fi

if EXISTING=$(timeout 15 ros2 topic list 2>&1); then LIST_RC=0; else LIST_RC=$?; fi
if [[ $LIST_RC -ne 0 ]]; then echo "WARNING: ros2 topic list failed (exit $LIST_RC); per-topic checks below are skipped, not absent:"; echo "$EXISTING"; EXISTING=""; fi
for t in "${CANDIDATES[@]}"; do
  [[ "$t" == "/clock" ]] && continue
  if ! grep -qx "$t" <<<"$EXISTING"; then echo "skip $t ($([[ $LIST_RC -eq 0 ]] && echo not present || echo topic list failed))"; continue; fi
  f="$OUT/topic$(echo "$t" | tr '/' '_').txt"
  {
  run "info -v $t" timeout 15 ros2 topic info -v "$t"
  run "hz $t (8 s)" timeout 8 ros2 topic hz "$t" --window 20
  run "sample $t" timeout 10 ros2 topic echo --once --no-arr "$t"
  } | tee "$f"
done

{
run "tf2_echo odom -> base_link (5 s)" timeout 5 ros2 run tf2_ros tf2_echo odom base_link
run "tf frames yaml" bash -c 'timeout 12 ros2 run tf2_ros tf2_echo --help >/dev/null 2>&1; timeout 15 ros2 topic echo --once --no-arr /tf_static'
} | tee "$OUT/02-tf.txt"

echo
echo "=== summary: clock_advancing=$CLOCK_OK files in $OUT: $(ls "$OUT" | tr '\n' ' ') ==="
[[ $CLOCK_OK -eq 1 ]]
