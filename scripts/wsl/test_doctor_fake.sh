#!/usr/bin/env bash
# test_doctor_fake.sh - RoboSim Eval D1: fake-node integration test of the doctor (ROS 2 only, no Isaac Sim).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_doctor_fake.sh <out_dir>
# Runs tests/ros_fake/fake_isaac.py on the isolated ROS domain 42 (the real Isaac data on domain 0 is not touched) and
# checks the doctor's exit code and wall time for: healthy 0; paused 10; closed (no publisher) 11; lidar publisher
# missing 11; slow lidar 12; RMW_IMPLEMENTATION unset 13. Every doctor run must finish within MAX_S seconds: the
# designed bound is discovery_timeout_s (5) + window_s (5) + about 3 s of Python/rclpy start-up and shutdown.
# Each fake runs in its own session and is stopped (INT, then KILL) only through that session id.
# Exit: 0 all cases as expected; 1 at least one case differs; 2 setup failure.
set -uo pipefail
OUT="${1:?out dir}"
REPO=/mnt/d/RoboSim-Eval
MAX_S=15
mkdir -p "$OUT" || exit 2
exec > >(tee "$OUT/summary.txt") 2>&1   # keep the result table next to the per-case logs
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
export ROS_DOMAIN_ID=42 PYTHONDONTWRITEBYTECODE=1
cd "$REPO" || exit 2
CFG="$REPO/tests/ros_fake/doctor_fake.yaml"
FAKE_SID=""

start_fake() {  # start_fake <name> [fake args...]; the fake leads its own session
  local name="$1"; shift
  setsid python3 tests/ros_fake/fake_isaac.py --duration 40 "$@" > "$OUT/fake-$name.log" 2>&1 < /dev/null &
  FAKE_SID=$!
  sleep 1.5
}
stop_fake() {
  [[ -z "$FAKE_SID" ]] && return 0
  pkill -INT -s "$FAKE_SID" 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -s "$FAKE_SID" >/dev/null || break; sleep 0.2; done
  pkill -KILL -s "$FAKE_SID" 2>/dev/null
  wait "$FAKE_SID" 2>/dev/null
  FAKE_SID=""
}
trap stop_fake EXIT

FAILS=0
check() {  # check <case> <expected rc> [env assignments...] -- runs the doctor, compares rc and wall time
  local case="$1" want="$2"; shift 2
  local t0 t1 rc secs verdict
  t0=$(date +%s.%N)
  env "$@" python3 -m robosim_eval.doctor --config "$CFG" --out "$OUT/$case" > "$OUT/doctor-$case.txt" 2>&1
  rc=$?
  t1=$(date +%s.%N)
  secs=$(python3 -c 'import sys; print(f"{float(sys.argv[2]) - float(sys.argv[1]):.1f}")' "$t0" "$t1")
  verdict="PASS"
  if [[ "$rc" != "$want" ]]; then verdict="FAIL"; FAILS=$((FAILS + 1)); fi
  if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) <= float(sys.argv[2]) else 1)' "$secs" "$MAX_S"; then :; else
    verdict="FAIL(time)"; FAILS=$((FAILS + 1)); fi
  printf '%-22s expected %-3s got %-3s %6ss  %s  (%s)\n' "$case" "$want" "$rc" "$secs" "$verdict" \
    "$(grep -m1 '^verdict:' "$OUT/doctor-$case.txt")"
}

echo "=== test_doctor_fake.sh $(date -Is) ROS_DOMAIN_ID=$ROS_DOMAIN_ID max ${MAX_S}s per doctor run ==="
start_fake healthy; check healthy 0; stop_fake
start_fake paused --pause-after 0.5; check paused 10; stop_fake
check closed 11
start_fake nolidar --no-lidar; check lidar_missing 11; stop_fake
start_fake slowlidar --lidar-hz 0.5; check lidar_slow 12; stop_fake
start_fake envcheck; check rmw_unset 13 -u RMW_IMPLEMENTATION; stop_fake
echo "=== result: $([[ $FAILS -eq 0 ]] && echo PASS || echo "FAIL ($FAILS)") ==="
[[ $FAILS -eq 0 ]]
