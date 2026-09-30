# ros_env.sh — RoboSim Eval: ROS 2 Jazzy environment for WSL Ubuntu terminals (plan doc B2 + B3).
# SOURCE this file in every new Ubuntu terminal; it never edits ~/.bashrc:
#   source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh              # /opt/ros/jazzy + pinned Isaac workspace overlay
#   source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only  # /opt/ros/jazzy only (before the overlay is built)
# Returns non-zero and prints the missing path when something required is absent.
# The Windows<->WSL Fast DDS profile is separate: source dds_env.sh after this file (plan doc B4).

_robosim_fail() { echo "ros_env.sh: $1" >&2; return 1; }

_robosim_ws="${ROBOSIM_VENDOR_WS:-$HOME/robotics/vendor/isaac-ros-6.1/jazzy_ws}"
_robosim_mode="${1:-full}"

if [ ! -f /opt/ros/jazzy/setup.bash ]; then
  _robosim_fail "/opt/ros/jazzy/setup.bash not found (ROS 2 Jazzy is not installed)"; return 1 2>/dev/null || exit 1
fi
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash

if [ "$_robosim_mode" != "--base-only" ]; then
  if [ ! -f "$_robosim_ws/install/setup.bash" ]; then
    _robosim_fail "overlay $_robosim_ws/install/setup.bash not found (workspace not built; use --base-only until then)"; return 1 2>/dev/null || exit 1
  fi
  # shellcheck disable=SC1091
  source "$_robosim_ws/install/setup.bash"
fi

export ROS_DISTRO=jazzy
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=0
unset ROS_LOCALHOST_ONLY

echo "ros_env.sh: ROS_DISTRO=$ROS_DISTRO RMW_IMPLEMENTATION=$RMW_IMPLEMENTATION ROS_DOMAIN_ID=$ROS_DOMAIN_ID mode=$_robosim_mode overlay=$_robosim_ws"
unset _robosim_mode
