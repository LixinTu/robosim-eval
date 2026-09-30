# ros_env.sh — RoboSim Eval: ROS 2 Jazzy environment for WSL Ubuntu terminals (plan doc B2 + B3).
# SOURCE this file; it never edits ~/.bashrc:
#   source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full        # /opt/ros/jazzy + pinned Isaac workspace overlay
#   source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only   # /opt/ros/jazzy only (e.g. before the overlay exists)
#   source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh               # interactive terminals only: same as --full
# Scripts must pass the mode explicitly: a bare `source` inside a script sees that SCRIPT's positional parameters
# (e.g. an attempt directory), which is rejected here instead of being silently used as the mode.
# Returns non-zero and prints the problem when the mode is unknown or a required path is absent.
# The Windows<->WSL Fast DDS profile is separate: source dds_env.sh after this file (plan doc B4).

_robosim_fail() { echo "ros_env.sh: $1" >&2; }

case "${1:-}" in
  --base-only) _robosim_mode=base-only ;;
  --full|"")   _robosim_mode=full ;;
  *) _robosim_fail "unknown mode '$1' (use --full or --base-only; scripts must pass one explicitly)"; return 2 2>/dev/null || exit 2 ;;
esac

_robosim_ws="${ROBOSIM_VENDOR_WS:-$HOME/robotics/vendor/isaac-ros-6.1/jazzy_ws}"

if [ ! -f /opt/ros/jazzy/setup.bash ]; then
  _robosim_fail "/opt/ros/jazzy/setup.bash not found (ROS 2 Jazzy is not installed)"; return 1 2>/dev/null || exit 1
fi
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash

if [ "$_robosim_mode" = full ]; then
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
