#!/usr/bin/env bash
# test_runner_fake.sh - RoboSim Eval D2: fake-node test of the runner's state machine (ROS 2 only, no Isaac, no Nav2).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_runner_fake.sh <out_dir>
# On the isolated ROS domain 42: tests/ros_fake/fake_isaac.py (clock, odom, tf, lidar) plus tests/ros_fake/fake_nav2.py
# (NavigateToPose action server) in different modes, then `robosim_eval.runner --no-sim --no-nav2 --no-record
# --no-analyze` with tests/ros_fake/runner_fake.yaml (short timeouts). Checks the runner exit code, the execution
# status and the terminal/timeout facts in result.json for: succeed, abort, nav timeout, reject, interrupt (SIGINT),
# cancel ignored, robot never at rest, no action server. Fakes are stopped only through their own session ids.
# Exit: 0 all cases as expected; 1 at least one differs; 2 setup failure.
set -uo pipefail
OUT="${1:?out dir}"
REPO=/mnt/d/RoboSim-Eval
mkdir -p "$OUT" || exit 2
exec > >(tee "$OUT/summary.txt") 2>&1
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
export ROS_DOMAIN_ID=42 ROBOSIM_DOCTOR_DOMAIN=42 PYTHONDONTWRITEBYTECODE=1
cd "$REPO" || exit 2
CFG="$REPO/tests/ros_fake/runner_fake.yaml"
SIDS=()
start() {  # start <log name> <python file> [args...]
  local name="$1"; shift
  setsid python3 "$@" > "$OUT/$name.log" 2>&1 < /dev/null &
  SIDS+=($!)
}
stop_all() {
  local s
  for s in "${SIDS[@]}"; do pkill -INT -s "$s" 2>/dev/null; done
  sleep 1
  for s in "${SIDS[@]}"; do pkill -KILL -s "$s" 2>/dev/null; wait "$s" 2>/dev/null; done
  SIDS=()
}
trap stop_all EXIT

FAILS=0
check() {  # check <case> <expected exit> <expected execution_status> <jq-like python expr on result or ""> [sigint_after_s]
  local case="$1" want_rc="$2" want_exec="$3" expr="$4" sigint="${5:-}"
  local dir="$OUT/$case" t0 rc
  mkdir -p "$dir"
  t0=$(date +%s)
  python3 -m robosim_eval.runner --scenario fake --config "$CFG" --out "$dir" --no-sim --no-nav2 --no-record \
    --no-analyze > "$dir/runner.txt" 2>&1 &
  local pid=$!
  if [[ -n "$sigint" ]]; then sleep "$sigint"; kill -INT "$pid" 2>/dev/null; fi
  wait "$pid"; rc=$?
  local res; res=$(ls "$dir"/fake-*/result.json 2>/dev/null | head -1)
  local got_exec; got_exec=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["execution_status"])' "$res" 2>/dev/null)
  local extra_ok=1
  if [[ -n "$expr" ]]; then
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' "$res" "$expr" \
      2>/dev/null || extra_ok=0
  fi
  local verdict=PASS
  if [[ "$rc" != "$want_rc" || "$got_exec" != "$want_exec" || $extra_ok -ne 1 ]]; then verdict=FAIL; FAILS=$((FAILS + 1)); fi
  printf '%-16s exit %-3s (want %-3s) execution %-12s (want %-12s) check %s  %3ss  %s\n' "$case" "$rc" "$want_rc" \
    "$got_exec" "$want_exec" "$([[ $extra_ok -eq 1 ]] && echo ok || echo FAILED)" "$(( $(date +%s) - t0 ))" "$verdict"
}

echo "=== test_runner_fake.sh $(date -Is) ROS_DOMAIN_ID=$ROS_DOMAIN_ID ==="
start isaac tests/ros_fake/fake_isaac.py --duration 600
sleep 1.5
start nav2-succeed tests/ros_fake/fake_nav2.py --mode succeed --duration 2
check succeed 11 completed 'r["runner"]["terminal"]["name"] == "SUCCEEDED" and r["runner"]["states"][-1]["state"] == "DONE"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-abort tests/ros_fake/fake_nav2.py --mode abort --duration 2
check abort 11 completed 'r["runner"]["terminal"]["name"] == "ABORTED" and r["runner"]["terminal"]["error_code"] == 208'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-never tests/ros_fake/fake_nav2.py --mode never
check nav_timeout 10 completed 'r["task_outcome"] == "timeout" and r["runner"]["timeout_reason"] == "nav_wall_timeout" and r["runner"]["terminal"]["name"] == "CANCELED"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-reject tests/ros_fake/fake_nav2.py --mode reject
check reject 11 completed 'any(s["reason"] == "goal rejected" for s in r["runner"]["states"])'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-never2 tests/ros_fake/fake_nav2.py --mode never
check interrupt 20 interrupted 'r["runner"]["interrupted_by"] == "SIGINT" and r["runner"]["terminal"]["name"] == "CANCELED"' 9
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-ignore tests/ros_fake/fake_nav2.py --mode ignore-cancel
check cancel_ignored 31 error 'r["runner"]["abort_batch"] and "cancel_timeout" in r["runner"]["errors"]'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600 --moving; sleep 1.5
start nav2-succeed2 tests/ros_fake/fake_nav2.py --mode succeed --duration 2
check never_at_rest 31 error 'r["runner"]["abort_batch"] and "stop_timeout" in r["runner"]["errors"]'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
check no_server 30 error '"ready_timeout" in r["runner"]["errors"]'
stop_all
echo "=== result: $([[ $FAILS -eq 0 ]] && echo PASS || echo "FAIL ($FAILS)") ==="
[[ $FAILS -eq 0 ]]
