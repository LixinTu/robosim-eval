#!/usr/bin/env bash
# probe_env.sh — RoboSim Eval D0a: read-only environment probes (WSL side). Makes no changes.
# Usage (from Windows PowerShell), run twice to compare login vs clean environments:
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_env.sh
#   wsl -d Ubuntu -- bash --noprofile --norc /mnt/d/RoboSim-Eval/scripts/wsl/probe_env.sh
# Each section prints the command, its output and the command's own exit code (never masked).
set -u

run() {   # run "<title>" <command...>
  local title="$1"; shift
  echo; echo "===== $title ====="; echo "CMD: $*"
  local out rc
  out=$("$@" 2>&1); rc=$?
  printf '%s\n' "$out"; echo "EXIT: $rc"
}
runsh() { # runsh "<title>" '<bash snippet>'
  local title="$1" snippet="$2"
  echo; echo "===== $title ====="; echo "CMD: $snippet"
  local out rc
  out=$(bash -c "$snippet" 2>&1); rc=$?
  printf '%s\n' "$out"; echo "EXIT: $rc"
}

login=no; shopt -q login_shell && login=yes
interactive=no; [[ $- == *i* ]] && interactive=yes
echo "PROBE START: $(date -Is)  script=$0  login_shell=$login  interactive=$interactive"

run   "identity" id
runsh "home/shell" 'echo "HOME=$HOME USER=${USER:-?} SHELL=${SHELL:-?} PWD=$PWD"'
run   "os-release" cat /etc/os-release
run   "kernel" uname -r
run   "python3" python3 --version
run   "git" git --version
runsh "colcon" 'command -v colcon || echo "colcon not on PATH"'
runsh "ros2 before source" 'command -v ros2 || echo "ros2 not on PATH (before source)"'
run   "opt ros" ls -ld /opt/ros /opt/ros/jazzy
runsh "ros2 after source" 'if [ -f /opt/ros/jazzy/setup.bash ]; then source /opt/ros/jazzy/setup.bash && command -v ros2 && echo "ROS_DISTRO=$ROS_DISTRO RMW=${RMW_IMPLEMENTATION:-unset}"; else echo "no /opt/ros/jazzy/setup.bash"; fi'
runsh "ros-jazzy package count" 'dpkg-query -W -f="\${Package}\n" "ros-jazzy-*" 2>/dev/null | wc -l'
for p in ros-jazzy-desktop ros-dev-tools ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-nav2-simple-commander ros-jazzy-pointcloud-to-laserscan ros-jazzy-rmw-fastrtps-cpp ros-jazzy-demo-nodes-cpp ros-jazzy-rviz2 python3-colcon-common-extensions python3-rosdep; do
  runsh "pkg $p" "dpkg-query -W -f='\${Status} \${Version}\n' $p 2>/dev/null || echo 'not installed'; apt-cache policy $p 2>/dev/null | sed -n '2,3p'"
done
runsh "apt sources mentioning ros" 'ls -la /etc/apt/sources.list.d/ 2>/dev/null; grep -rHi ros /etc/apt/sources.list.d/ /etc/apt/sources.list 2>/dev/null || echo "no ros apt source"'
runsh "rosdep state" 'ls -la /etc/ros/rosdep/sources.list.d/ 2>&1; ls -la ~/.ros/rosdep/ 2>&1'
run   "sudo -n true" sudo -n true
runsh "display vars" 'echo "DISPLAY=${DISPLAY:-unset} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-unset} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-unset}"; ls -la /mnt/wslg 2>&1 | head -5'
runsh "ip" 'ip -4 addr show 2>/dev/null | grep -E "inet |^[0-9]+:"; echo "--- route ---"; ip route 2>/dev/null | head -5'
run   "memory" free -h
run   "disk" df -h / /mnt/d
runsh "existing workspaces" 'ls -ld ~/robotics ~/robotics/vendor ~/robotics/vendor/* 2>&1; echo "--- find ---"; find ~ -maxdepth 4 -type d \( -name "IsaacSim-ros_workspaces*" -o -name "isaac-ros-6.1" -o -name jazzy_ws \) 2>/dev/null; find /mnt/d -maxdepth 2 -type d \( -name "IsaacSim-ros_workspaces*" -o -name "isaac-ros-6.1" -o -name jazzy_ws \) 2>/dev/null; true'
runsh "residual ROS/DDS env" 'env | grep -E "ROS_|RMW_|FASTRTPS|CYCLONE|DDS" || echo "none in env"'
runsh "residual ROS lines in rc files" 'grep -nE "ros|RMW|ROS_|FASTRTPS" ~/.bashrc ~/.profile /etc/environment /etc/profile.d/* 2>/dev/null || echo "none in rc files"'
runsh "existing fastdds xml" 'ls -la ~/.ros/*.xml /mnt/d/robosim-assets/network/*.xml 2>&1'
runsh "rviz2 binary" 'command -v rviz2 || ls -la /opt/ros/jazzy/bin/rviz2 2>&1 || echo "rviz2 not found"'
runsh "network reachability (github, ros apt)" 'for h in github.com packages.ros.org; do if getent hosts "$h" >/dev/null 2>&1; then echo "$h resolves"; else echo "$h does NOT resolve"; fi; done'

echo; echo "PROBE END: $(date -Is)"
