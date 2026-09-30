#!/usr/bin/env bash
# check_ros_install.sh — RoboSim Eval D0b: verify the ROS 2 Jazzy installation in WSL (read-only, no sudo).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_ros_install.sh
# Exit code is non-zero when any required executable or package is missing.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
rc=0
fail() { echo "FAIL: $*"; rc=1; }

echo "=== check_ros_install.sh $(date -Is) ==="
set +u
# shellcheck disable=SC1091
if ! source "$REPO/scripts/wsl/ros_env.sh" --base-only; then echo "FAIL: ros_env.sh --base-only"; exit 1; fi
set -u

echo "--- executables ---"
for exe in ros2 rviz2 colcon rosdep python3; do
  p=$(command -v "$exe" || true)
  if [[ -n "$p" ]]; then echo "ok   $exe -> $p"; else fail "$exe not on PATH"; fi
done

echo "--- packages (dpkg) ---"
PKGS=(ros-dev-tools ros-jazzy-desktop ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-nav2-simple-commander ros-jazzy-nav2-rviz-plugins ros-jazzy-pointcloud-to-laserscan ros-jazzy-rmw-fastrtps-cpp ros-jazzy-joint-state-publisher ros-jazzy-robot-state-publisher ros-jazzy-xacro ros-jazzy-ament-flake8 ros-jazzy-ament-pep257 ros-jazzy-demo-nodes-cpp python3-numpy python3-pil python3-pytest python3-yaml)
for p in "${PKGS[@]}"; do
  st=$(dpkg-query -W -f='${Status}|${Version}' "$p" 2>/dev/null || true)
  if [[ "$st" == install\ ok\ installed* ]]; then echo "ok   $p ${st#*|}"; else fail "$p: ${st:-not installed}"; fi
done

echo "--- ros2 package index ---"
for p in demo_nodes_cpp nav2_bringup pointcloud_to_laserscan rmw_fastrtps_cpp rviz2 nav2_msgs xacro; do
  if pre=$(ros2 pkg prefix "$p" 2>/dev/null); then echo "ok   $p -> $pre"; else fail "ros2 pkg prefix $p"; fi
done

echo "--- rosdep ---"
if [[ -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then echo "ok   rosdep initialized"; else fail "rosdep not initialized"; fi
if ls ~/.ros/rosdep/sources.cache/*.pickle >/dev/null 2>&1; then echo "ok   rosdep cache present"; else fail "rosdep cache missing (run: rosdep update)"; fi

echo "--- rmw ---"
echo "RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION ROS_DOMAIN_ID=$ROS_DOMAIN_ID ROS_DISTRO=$ROS_DISTRO"
if [[ -f /opt/ros/jazzy/lib/librmw_fastrtps_cpp.so ]]; then echo "ok   librmw_fastrtps_cpp.so present"; else fail "librmw_fastrtps_cpp.so missing"; fi

echo "=== result: $([[ $rc -eq 0 ]] && echo PASS || echo FAIL) ==="
exit $rc
