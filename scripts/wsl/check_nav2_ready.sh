#!/usr/bin/env bash
# check_nav2_ready.sh — RoboSim Eval D0d: readiness evidence and verdict for the Nav2 stack (plan doc B6 steps 1-2).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_nav2_ready.sh <run_dir>
# Everything is time-bounded and read-only. Writes <run_dir>/ready-<timestamp>.txt (the full output) and prints it.
# Part A (before initial pose): lifecycle states, /scan rate, /map (transient_local), use_sim_time params, action list,
#   odom->base_link TF, /clock rate. Part B (informational): map->odom->base_link TF and /amcl_pose, only meaningful once
#   AMCL is localized.
# Verdict (exit status): 0 ready = every listed lifecycle node reports "active", /navigate_to_pose is offered, /map was
#   received, /scan and /clock have a measured rate; 1 not ready (the failed items are listed at the end); 2 environment
#   or output-file problem.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
RUN_DIR="${1:?run dir required}"
mkdir -p "$RUN_DIR" || exit 2
OUT="$RUN_DIR/ready-$(date +%H%M%S).txt"
: > "$OUT" || { echo "cannot write $OUT"; exit 2; }
exec > >(tee -a "$OUT") 2>&1
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
NOT_READY=()
run() { local title="$1"; shift; echo; echo "===== $title ====="; echo "CMD: $*"; LAST=$("$@" 2>&1); LAST_RC=$?; echo "$LAST"; echo "EXIT: $LAST_RC"; }

echo "=== check_nav2_ready.sh $(date -Is) run_dir=$RUN_DIR ==="
run "node list" timeout 15 ros2 node list
for n in map_server amcl planner_server controller_server bt_navigator behavior_server smoother_server velocity_smoother collision_monitor waypoint_follower; do
  run "lifecycle $n" timeout 6 ros2 lifecycle get "/$n"
  [[ "$LAST" == active* ]] || NOT_READY+=("lifecycle /$n: ${LAST:-no answer}")
done
run "/scan hz (8 s)" timeout 8 ros2 topic hz /scan --window 20
grep -q 'average rate' <<<"$LAST" || NOT_READY+=("/scan: no measured rate")
run "/scan info" timeout 10 ros2 topic info -v /scan
run "/front_2d_lidar/scan hz (5 s, expected absent)" timeout 5 ros2 topic hz /front_2d_lidar/scan --window 5
run "/map once (transient_local)" timeout 15 ros2 topic echo --once --no-arr --qos-durability transient_local --qos-reliability reliable /map
[[ $LAST_RC -eq 0 ]] || NOT_READY+=("/map: not received (exit $LAST_RC)")
run "param use_sim_time amcl" timeout 6 ros2 param get /amcl use_sim_time
run "param use_sim_time controller_server" timeout 6 ros2 param get /controller_server use_sim_time
run "param amcl set_initial_pose" timeout 6 ros2 param get /amcl set_initial_pose
run "param amcl initial_pose.x/y/yaw" bash -c 'for k in initial_pose.x initial_pose.y initial_pose.yaw; do timeout 6 ros2 param get /amcl $k; done'
run "action list -t" timeout 15 ros2 action list -t
grep -q '^/navigate_to_pose \[nav2_msgs/action/NavigateToPose\]' <<<"$LAST" || NOT_READY+=("/navigate_to_pose [nav2_msgs/action/NavigateToPose] not offered")
run "/cmd_vel info" timeout 10 ros2 topic info -v /cmd_vel
run "tf odom -> base_link (4 s)" timeout 4 ros2 run tf2_ros tf2_echo odom base_link
run "tf map -> odom (6 s)" timeout 6 ros2 run tf2_ros tf2_echo map odom
run "tf map -> base_link (6 s)" timeout 6 ros2 run tf2_ros tf2_echo map base_link
run "/amcl_pose once (8 s)" timeout 8 ros2 topic echo --once --no-arr /amcl_pose
run "/clock hz (5 s)" timeout 5 ros2 topic hz /clock --window 20
grep -q 'average rate' <<<"$LAST" || NOT_READY+=("/clock: no measured rate (simulation not playing?)")
echo
if [[ ${#NOT_READY[@]} -eq 0 ]]; then
  echo "=== verdict: READY ($(date -Is)) ==="; RC=0
else
  echo "=== verdict: NOT READY ($(date -Is)) ==="; printf '  - %s\n' "${NOT_READY[@]}"; RC=1
fi
echo "written $OUT"
exit $RC
