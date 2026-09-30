#!/usr/bin/env bash
# test_talker_listener.sh — RoboSim Eval D0b: WSL-internal ROS 2 communication check (plan doc B2.4).
# Proves only that two ROS 2 nodes inside WSL can talk; it says nothing about Isaac Sim on Windows.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_talker_listener.sh [--with-dds-profile] [<out_dir>]
# --with-dds-profile additionally sources dds_env.sh so Fast DDS loads configs/network/fastdds.xml (UDPv4 only).
# Exit 0 = listener received messages; 1 = it did not. Both nodes run under `timeout`, whose exit code 124 means
# "ran for the full window" by design. Only the processes started here are stopped.
set -uo pipefail
WITH_DDS=no
[[ "${1:-}" == "--with-dds-profile" ]] && { WITH_DDS=yes; shift; }
OUT="${1:-/mnt/d/RoboSim-Eval/artifacts/d0b}"
mkdir -p "$OUT"
TAG=$([[ $WITH_DDS == yes ]] && echo "dds" || echo "default")
TLOG="$OUT/talker-$TAG.log"; LLOG="$OUT/listener-$TAG.log"

set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only || exit 2
if [[ $WITH_DDS == yes ]]; then
  # shellcheck disable=SC1091
  source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
fi
set -u

echo "=== test_talker_listener.sh $(date -Is) profile=$TAG RMW=$RMW_IMPLEMENTATION DOMAIN=$ROS_DOMAIN_ID FASTRTPS_DEFAULT_PROFILES_FILE=${FASTRTPS_DEFAULT_PROFILES_FILE:-unset} ==="
timeout 20 ros2 run demo_nodes_cpp talker > "$TLOG" 2>&1 &
TPID=$!
echo "talker started pid=$TPID (timeout 20 s) -> $TLOG"
sleep 2
timeout 12 ros2 run demo_nodes_cpp listener > "$LLOG" 2>&1
LRC=$?
echo "listener finished exit=$LRC (124 = ran the full 12 s window) -> $LLOG"
if kill -0 "$TPID" 2>/dev/null; then kill -INT "$TPID" 2>/dev/null; fi
wait "$TPID"; TRC=$?
echo "talker finished exit=$TRC (124 = full window, 130 = stopped by this script)"
HEARD=$(grep -c 'I heard' "$LLOG" || true)
PUBLISHED=$(grep -c 'Publishing' "$TLOG" || true)
echo "talker published lines: $PUBLISHED ; listener 'I heard' lines: $HEARD"
if [[ "$HEARD" -gt 0 ]]; then echo "=== result: PASS (WSL-internal only) ==="; exit 0; else echo "=== result: FAIL ==="; tail -5 "$TLOG" "$LLOG"; exit 1; fi
