#!/usr/bin/env bash
# install_ros2_jazzy.sh — RoboSim Eval D0b: install ROS 2 Jazzy + Nav2 dependencies in WSL Ubuntu 24.04 (noble).
#
# Run by the USER in an Ubuntu terminal (sudo will ask for the password once):
#   bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh            # default
#   bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh --with-upgrade   # only if apt install fails on held deps
#
# Source of the steps: ROS 2 Jazzy "Ubuntu (deb packages)" instructions, read 2026-09-29 from the official mirror
# https://repo.test.ros2.org/en/jazzy/Installation/Ubuntu-Install-Debs.html (docs.ros.org showed an anti-bot page).
# Deviations from the docs: no blanket `apt upgrade` by default (project rule: no unrelated system upgrades);
# locale steps only run when the current locale is not UTF-8; navigation packages needed by the pinned Isaac
# workspace are added. Re-running is safe: apt only installs what is missing.
#
# Log: $REPO/artifacts/d0b/install-jazzy.log ; exit code: .../install-jazzy.exit
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)

WITH_UPGRADE=no
[[ "${1:-}" == "--with-upgrade" ]] && WITH_UPGRADE=yes

LOG_DIR="$REPO/artifacts/d0b"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/install-jazzy.log"
exec > >(tee -a "$LOG") 2>&1
trap 'rc=$?; echo; echo "=== install_ros2_jazzy.sh end $(date -Is) exit=$rc ==="; echo "$rc" > "$LOG_DIR/install-jazzy.exit"' EXIT

echo "=== install_ros2_jazzy.sh start $(date -Is) user=$(id -un) with_upgrade=$WITH_UPGRADE ==="
step() { echo; echo "--- [$(date +%T)] $* ---"; }

step "0. preconditions"
. /etc/os-release
CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME}}"
echo "os: $PRETTY_NAME codename=$CODENAME"
if [[ "$CODENAME" != "noble" ]]; then echo "ERROR: expected Ubuntu noble (24.04), got $CODENAME"; exit 2; fi
sudo -v

step "1. locale (only if current LANG is not UTF-8)"
if ! locale 2>/dev/null | grep -q 'LANG=.*UTF-8'; then
  sudo apt-get update
  sudo apt-get install -y locales
  sudo locale-gen en_US en_US.UTF-8
  sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
  export LANG=en_US.UTF-8
fi
locale

step "2. enable universe repository and curl"
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y universe
sudo apt-get update
sudo apt-get install -y curl

step "3. ros2-apt-source"
if dpkg -s ros2-apt-source >/dev/null 2>&1; then
  echo "ros2-apt-source already installed: $(dpkg-query -W -f='${Version}' ros2-apt-source)"
else
  ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest | grep -F "tag_name" | awk -F\" '{print $4}')
  echo "ros-apt-source latest tag: ${ROS_APT_SOURCE_VERSION:-<empty>}"
  if [[ -z "$ROS_APT_SOURCE_VERSION" ]]; then echo "ERROR: could not resolve ros-apt-source version from the GitHub API"; exit 3; fi
  curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${CODENAME}_all.deb"
  sudo dpkg -i /tmp/ros2-apt-source.deb
fi
sudo apt-get update

if [[ "$WITH_UPGRADE" == "yes" ]]; then
  step "3b. apt upgrade (explicitly requested with --with-upgrade)"
  sudo apt-get upgrade -y
fi

step "4. install ROS 2 Jazzy desktop, dev tools, navigation packages and the carter_navigation dependency closure"
# Closure computed 2026-09-29 from package.xml of carter_navigation, isaacsim_bringup and isaac_ros_navigation_goal
# (IsaacSim-ros_workspaces tag IsaacSim-6.1.0, commit a9e8471); rosdep keys mapped to noble/jazzy apt names.
PKGS=(ros-dev-tools ros-jazzy-desktop
      ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-nav2-simple-commander ros-jazzy-nav2-rviz-plugins
      ros-jazzy-pointcloud-to-laserscan ros-jazzy-rmw-fastrtps-cpp
      ros-jazzy-joint-state-publisher ros-jazzy-robot-state-publisher ros-jazzy-xacro
      ros-jazzy-ament-flake8 ros-jazzy-ament-pep257
      python3-numpy python3-pil python3-pytest python3-yaml)
sudo apt-get install -y "${PKGS[@]}"

step "5. rosdep (init only if missing; update runs as the normal user)"
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then sudo rosdep init; else echo "rosdep already initialized"; fi
rosdep update

step "6. verification (each line must show 'install ok installed')"
for p in "${PKGS[@]}"; do printf '%-40s %s\n' "$p" "$(dpkg-query -W -f='${Status} ${Version}' "$p")"; done
# ROS setup scripts are not `set -u` clean (AMENT_TRACE_SETUP_FILES), so relax -u while sourcing.
set +u
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
set -u
echo "ros2 executable: $(command -v ros2)"
echo "colcon executable: $(command -v colcon)"
echo "rosdep: $(rosdep --version)"
echo "demo_nodes_cpp prefix: $(ros2 pkg prefix demo_nodes_cpp)"
echo "nav2_bringup prefix: $(ros2 pkg prefix nav2_bringup)"
echo "pointcloud_to_laserscan prefix: $(ros2 pkg prefix pointcloud_to_laserscan)"
echo "rmw_fastrtps_cpp prefix: $(ros2 pkg prefix rmw_fastrtps_cpp)"
echo "ALL STEPS COMPLETED"
