#!/usr/bin/env bash
# test_doctor_fake.sh - RoboSim Eval D1: fake-node integration test of the doctor (ROS 2 only, no Isaac Sim).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_doctor_fake.sh <out_dir>
# Runs tests/ros_fake/fake_isaac.py on an isolated ROS domain, ROBOSIM_TEST_DOMAIN (default 42; 0, the domain of the
# real Isaac data, is refused), and checks the doctor's exit code, first reason and wall time for: healthy 0; paused
# 10; closed (no publisher) 11; lidar publisher missing 11; slow lidar 12; RMW_IMPLEMENTATION unset 13; an extra
# publisher of another message type on /chassis/odom (sensor_msgs/msg/Imu) or on /clock (std_msgs/msg/Float64) 13;
# --window below clock_stall_s 2; a malformed config 2. The doctor, the fakes and the config come from the checkout this
# script is in (checked: python3 must import this checkout's doctor); the config is tests/ros_fake/doctor_fake.yaml
# with env.domain_id set to the test domain. Every doctor run must finish within MAX_S seconds: the designed bound is
# discovery_timeout_s (5) + window_s (5) + about 3 s of Python/rclpy start-up and shutdown.
# Each background process leads its own session and is stopped (INT, then KILL) only through that session id.
# Exit: 0 all cases as expected; 1 at least one case differs; 2 setup failure.
set -uo pipefail
OUT="${1:?out dir}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" || exit 2   # the checkout this script is in
DOMAIN="${ROBOSIM_TEST_DOMAIN:-42}"
MAX_S=15
if [[ ! "$DOMAIN" =~ ^[1-9][0-9]{0,2}$ ]] || (( DOMAIN > 232 )); then
  echo "test_doctor_fake.sh: ROBOSIM_TEST_DOMAIN must be 1-232, got '$DOMAIN'" >&2; exit 2
fi
mkdir -p "$OUT" || exit 2
exec > >(tee "$OUT/summary.txt") 2>&1   # keep the result table next to the per-case logs
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
export ROS_DOMAIN_ID="$DOMAIN" PYTHONDONTWRITEBYTECODE=1
cd "$REPO" || exit 2
DOCTOR_PY="$(python3 -c 'import robosim_eval.doctor as d; print(d.__file__)')" || exit 2
if [[ "$(realpath "$DOCTOR_PY")" != "$(realpath "$REPO/robosim_eval/doctor.py")" ]]; then
  echo "setup: python3 imports $DOCTOR_PY, not the doctor of $REPO"; exit 2
fi
CFG="$OUT/doctor_fake.yaml"
sed "s/domain_id: \"42\"/domain_id: \"$DOMAIN\"/" "$REPO/tests/ros_fake/doctor_fake.yaml" > "$CFG" || exit 2
grep -q "domain_id: \"$DOMAIN\"" "$CFG" || { echo "setup: could not set domain_id $DOMAIN in $CFG"; exit 2; }
BAD_CFG="$OUT/doctor_fake_malformed.yaml"
printf 'env: [1\n' > "$BAD_CFG" || exit 2

# An extra publisher of another message type on a configured topic: sys.argv = [topic, type]
WRONG_TYPE_PUB='
import sys, time
import rclpy
from rosidl_runtime_py.utilities import get_message
topic, type_name = sys.argv[1], sys.argv[2]
rclpy.init()
node = rclpy.create_node("robosim_wrong_type_publisher")
pub = node.create_publisher(get_message(type_name), topic, 10)
msg = get_message(type_name)()
end = time.monotonic() + 40.0
try:
    while rclpy.ok() and time.monotonic() < end:
        pub.publish(msg)
        rclpy.spin_once(node, timeout_sec=0.1)
except KeyboardInterrupt:
    pass
finally:
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
'

SIDS=()
start_bg() {  # start_bg <log name> <command...>; the process leads its own session
  local name="$1"; shift
  setsid "$@" > "$OUT/$name.log" 2>&1 < /dev/null &
  SIDS+=("$!")
}
start_fake() {  # start_fake <name> [fake args...]
  local name="$1"; shift
  start_bg "fake-$name" python3 tests/ros_fake/fake_isaac.py --duration 40 "$@"
  sleep 1.5
}
start_wrong_type() {  # start_wrong_type <name> <topic> <message type>
  start_bg "wrong-type-$1" python3 -c "$WRONG_TYPE_PUB" "$2" "$3"
  sleep 1.0
}
stop_all() {
  local s alive
  for s in "${SIDS[@]}"; do pkill -INT -s "$s" 2>/dev/null; done
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    alive=0
    for s in "${SIDS[@]}"; do if pgrep -s "$s" >/dev/null; then alive=1; fi; done
    if [[ $alive -eq 0 ]]; then break; fi
    sleep 0.2
  done
  for s in "${SIDS[@]}"; do pkill -KILL -s "$s" 2>/dev/null; wait "$s" 2>/dev/null; done
  SIDS=()
}
trap stop_all EXIT

FAILS=0
check() {  # check <case> <expected rc> <reason regex or ''> [VAR=value | -u VAR]... [-- doctor args...]
  local case="$1" want="$2" reason="$3"; shift 3
  local envs=() t0 t1 rc secs verdict
  while [[ $# -gt 0 && "$1" != "--" ]]; do envs+=("$1"); shift; done
  if [[ $# -gt 0 ]]; then shift; fi
  t0=$(date +%s.%N)
  env "${envs[@]}" python3 -m robosim_eval.doctor --config "$CFG" --out "$OUT/$case" "$@" > "$OUT/doctor-$case.txt" 2>&1
  rc=$?
  t1=$(date +%s.%N)
  secs=$(python3 -c 'import sys; print(f"{float(sys.argv[2]) - float(sys.argv[1]):.1f}")' "$t0" "$t1")
  verdict="PASS"
  if [[ "$rc" != "$want" ]]; then verdict="FAIL"; FAILS=$((FAILS + 1)); fi
  if [[ -n "$reason" ]] && ! grep -qE -e "$reason" "$OUT/doctor-$case.txt"; then
    verdict="FAIL(reason)"; FAILS=$((FAILS + 1)); fi
  if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) <= float(sys.argv[2]) else 1)' "$secs" "$MAX_S"; then :; else
    verdict="FAIL(time)"; FAILS=$((FAILS + 1)); fi
  printf '%-18s expected %-3s got %-3s %6ss  %-12s (%s | %s)\n' "$case" "$want" "$rc" "$secs" "$verdict" \
    "$(grep -m1 -E '^verdict:|ERROR' "$OUT/doctor-$case.txt")" "$(grep -m1 '^reason:' "$OUT/doctor-$case.txt")"
}

echo "=== test_doctor_fake.sh $(date -Is) ROS_DOMAIN_ID=$ROS_DOMAIN_ID max ${MAX_S}s per doctor run ==="
echo "doctor module: $DOCTOR_PY"
start_fake healthy; check healthy 0 ''; stop_all
start_fake paused --pause-after 0.5; check paused 10 '^reason: clock:'; stop_all
check closed 11 '^reason: clock: no publisher'
start_fake nolidar --no-lidar; check lidar_missing 11 '^reason: lidar: no publisher'; stop_all
start_fake slowlidar --lidar-hz 0.5; check lidar_slow 12 '^reason: lidar:'; stop_all
start_fake envcheck; check rmw_unset 13 '^reason: RMW_IMPLEMENTATION' -u RMW_IMPLEMENTATION; stop_all
start_fake odomtype; start_wrong_type odom /chassis/odom sensor_msgs/msg/Imu
check odom_wrong_type 13 '^reason: odom: publisher message type sensor_msgs/msg/Imu'; stop_all
start_fake clocktype; start_wrong_type clock /clock std_msgs/msg/Float64
check clock_wrong_type 13 '^reason: clock: publisher message type std_msgs/msg/Float64'; stop_all
check window_short 2 'usage error: --window' -- --window 0.5
check config_malformed 2 'config error: .*invalid YAML' -- --config "$BAD_CFG"
echo "=== result: $([[ $FAILS -eq 0 ]] && echo PASS || echo "FAIL ($FAILS)") ==="
[[ $FAILS -eq 0 ]]
