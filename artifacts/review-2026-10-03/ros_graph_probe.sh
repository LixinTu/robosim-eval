#!/usr/bin/env bash
# Read-only: which Isaac ROS 2 nodes and services WSL can discover (one-way discovery = inbound to kit.exe blocked).
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only || exit 2
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
echo "ROS_DOMAIN_ID=$ROS_DOMAIN_ID RMW=$RMW_IMPLEMENTATION profile=$FASTRTPS_DEFAULT_PROFILES_FILE"
ip -4 -o addr show eth0 | awk '{print "wsl eth0:", $4}'
ip route | awk '/default/ {print "gateway (Windows side):", $3}'
echo "--- nodes"
timeout 40 ros2 node list --no-daemon --spin-time 8; echo "node list exit $?"
echo "--- services"
timeout 40 ros2 service list --no-daemon --spin-time 8 | head -20; echo "service list exit ${PIPESTATUS[0]}"
