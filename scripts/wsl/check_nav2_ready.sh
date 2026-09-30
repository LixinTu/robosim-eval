#!/usr/bin/env bash
# check_nav2_ready.sh — RoboSim Eval D0d: readiness evidence for the Nav2 stack (plan doc B6 steps 1-2, A4 D0d).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_nav2_ready.sh <run_dir>
# Everything is time-bounded and read-only. Writes <run_dir>/ready-<timestamp>.txt and prints it.
# Part A (before initial pose): lifecycle states, /scan and 2D scans, /map (transient_local), use_sim_time params,
#   action list with types, odom->base_link TF. Part B: map->odom->base_link TF (only valid once AMCL is localized).
set -uo pipefail
RUN_DIR="${1:?run dir required}"
OUT="$RUN_DIR/ready-$(date +%H%M%S).txt"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
run() { local title="$1"; shift; echo; echo "===== $title ====="; echo "CMD: $*"; "$@"; echo "EXIT: $?"; }
{
echo "=== check_nav2_ready.sh $(date -Is) run_dir=$RUN_DIR ==="
run "node list" timeout 15 ros2 node list
for n in map_server amcl planner_server controller_server bt_navigator behavior_server smoother_server velocity_smoother collision_monitor waypoint_follower; do
  run "lifecycle $n" timeout 6 ros2 lifecycle get "/$n"
done
run "/scan hz (8 s)" timeout 8 ros2 topic hz /scan --window 20
run "/scan info" timeout 10 ros2 topic info -v /scan
run "/front_2d_lidar/scan hz (5 s, expected absent)" timeout 5 ros2 topic hz /front_2d_lidar/scan --window 5
run "/map once (transient_local)" timeout 15 ros2 topic echo --once --no-arr --qos-durability transient_local --qos-reliability reliable /map
run "param use_sim_time amcl" timeout 6 ros2 param get /amcl use_sim_time
run "param use_sim_time controller_server" timeout 6 ros2 param get /controller_server use_sim_time
run "param amcl set_initial_pose" timeout 6 ros2 param get /amcl set_initial_pose
run "param amcl initial_pose.x/y/yaw" bash -c 'for k in initial_pose.x initial_pose.y initial_pose.yaw; do timeout 6 ros2 param get /amcl $k; done'
run "action list -t" timeout 15 ros2 action list -t
run "/cmd_vel info" timeout 10 ros2 topic info -v /cmd_vel
run "tf odom -> base_link (4 s)" timeout 4 ros2 run tf2_ros tf2_echo odom base_link
run "tf map -> odom (6 s)" timeout 6 ros2 run tf2_ros tf2_echo map odom
run "tf map -> base_link (6 s)" timeout 6 ros2 run tf2_ros tf2_echo map base_link
run "/amcl_pose once (8 s)" timeout 8 ros2 topic echo --once --no-arr /amcl_pose
run "/clock hz (5 s)" timeout 5 ros2 topic hz /clock --window 20
echo; echo "=== end $(date -Is) ==="
} 2>&1 | tee "$OUT"
echo "written $OUT"
