#!/usr/bin/env bash
# test_runner_fake.sh - RoboSim Eval D2: fake-node test of the runner's state machine (ROS 2 only, no Isaac, no Nav2).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_runner_fake.sh <out_dir>
# On an isolated ROS domain (ROBOSIM_TEST_DOMAIN, default 42; never the real domain 0): tests/ros_fake/fake_isaac.py
# (clock, odom, tf, lidar) plus tests/ros_fake/fake_nav2.py (NavigateToPose action server) in different modes, then
# `robosim_eval.runner --no-sim --no-nav2 --no-record --no-analyze` with tests/ros_fake/runner_fake.yaml (short
# timeouts; its domain set to the test domain). Checks the runner exit code, the execution status and the facts in
# result.json for: succeed, abort, nav timeout, reject, interrupt (SIGINT), cancel ignored, robot never at rest, no
# action server, (D5) a declared Nav2 parameter change found in effect or not, and (review round 2) a goal accepted
# after the acceptance deadline, an internal error while the goal executes (cancel honoured or ignored), and a real
# terminal Ctrl-C through scripts/wsl/run_scenario.sh on a pseudo-terminal. Every case also checks that the runner
# that ran is this checkout's (manifest.json code.repo). Fakes are stopped only through their own session ids.
# Exit: 0 all cases as expected; 1 at least one differs; 2 setup failure.
set -uo pipefail
OUT="${1:?out dir}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # the checkout this script is in
DOMAIN="${ROBOSIM_TEST_DOMAIN:-42}"
[[ "$DOMAIN" =~ ^[0-9]+$ && "$DOMAIN" != 0 ]] || { echo "ROBOSIM_TEST_DOMAIN must be a number other than 0"; exit 2; }
mkdir -p "$OUT" || exit 2
exec > >(tee "$OUT/summary.txt") 2>&1
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only >/dev/null || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" >/dev/null || exit 2
set -u
export ROS_DOMAIN_ID="$DOMAIN" ROBOSIM_DOCTOR_DOMAIN="$DOMAIN" PYTHONDONTWRITEBYTECODE=1
cd "$REPO" || exit 2
CFG="$OUT/runner_fake.yaml"   # runner_fake.yaml on the test domain (the doctor checks env.domain_id)
sed -E "s/domain_id: \"[0-9]+\"/domain_id: \"$DOMAIN\"/" "$REPO/tests/ros_fake/runner_fake.yaml" > "$CFG" || exit 2
grep -q "domain_id: \"$DOMAIN\"" "$CFG" || { echo "could not set the test domain in $CFG"; exit 2; }
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
verdict() {  # verdict <case> <rc> <want rc> <want execution> <result.json> <expr> <t0>
  local case="$1" rc="$2" want_rc="$3" want_exec="$4" res="$5" expr="$6" t0="$7" got_exec extra_ok=1 own=ok
  got_exec=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["execution_status"])' "$res" 2>/dev/null)
  if [[ -n "$expr" ]]; then
    python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if eval(sys.argv[2]) else 1)' "$res" "$expr" \
      2>/dev/null || extra_ok=0
  fi
  python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); sys.exit(0 if m["code"]["repo"] == sys.argv[2] else 1)' \
    "$(dirname "$res")/manifest.json" "$REPO" 2>/dev/null || own="OTHER-CHECKOUT"
  local v=PASS
  if [[ "$rc" != "$want_rc" || "$got_exec" != "$want_exec" || $extra_ok -ne 1 || "$own" != ok ]]; then v=FAIL; FAILS=$((FAILS + 1)); fi
  printf '%-20s exit %-3s (want %-3s) execution %-12s (want %-12s) check %-6s code %-3s %3ss  %s\n' "$case" "$rc" \
    "$want_rc" "$got_exec" "$want_exec" "$([[ $extra_ok -eq 1 ]] && echo ok || echo FAILED)" "$own" \
    "$(( $(date +%s) - t0 ))" "$v"
}
check() {  # check <case> <expected exit> <expected execution_status> <python expr on result or ""> [sigint_after_s]
  local case="$1" want_rc="$2" want_exec="$3" expr="$4" sigint="${5:-}"
  local dir="$OUT/$case" t0 rc
  mkdir -p "$dir"
  t0=$(date +%s)
  # shellcheck disable=SC2086  # EXTRA holds extra runner switches, split on purpose
  python3 -m robosim_eval.runner --scenario "${SCEN:-fake}" --config "$CFG" --out "$dir" --no-sim --no-nav2 --no-record \
    --no-analyze ${EXTRA:-} > "$dir/runner.txt" 2>&1 &
  local pid=$!
  if [[ -n "$sigint" ]]; then sleep "$sigint"; kill -INT "$pid" 2>/dev/null; fi
  wait "$pid"; rc=$?
  verdict "$case" "$rc" "$want_rc" "$want_exec" "$(ls "$dir"/"${SCEN:-fake}"-*/result.json 2>/dev/null | head -1)" "$expr" "$t0"
}
pty_check() {  # a terminal Ctrl-C through run_scenario.sh (bash -l, as documented) once the goal executes
  local case="pty_ctrl_c" dir="$OUT/pty_ctrl_c" t0 rc
  mkdir -p "$dir"
  t0=$(date +%s)
  rc=$(ROBOSIM_RUN_DOMAIN="$DOMAIN" python3 - "$REPO/scripts/wsl/run_scenario.sh" "$dir" "$CFG" <<'PY'
import glob, os, pty, select, signal, sys, time
script, out, cfg = sys.argv[1:4]
pid, fd = pty.fork()
if pid == 0:  # session leader with the pty as its controlling terminal, as a wsl.exe console session
    os.execvp("bash", ["bash", "-l", script, "fake", "--config", cfg, "--out", out, "--no-sim", "--no-nav2",
                       "--no-record", "--no-analyze"])
term, t0, sent = open(os.path.join(out, "terminal.txt"), "wb"), time.monotonic(), None
while True:
    if select.select([fd], [], [], 0.1)[0]:
        try:
            term.write(os.read(fd, 4096))
        except OSError:
            pass
    if sent is None and any('"state": "EXECUTING"' in open(p).read() for p in glob.glob(f"{out}/fake-*/events.jsonl")):
        time.sleep(1.0)
        os.write(fd, b"\x03")
        sent = time.monotonic()
    done, status = os.waitpid(pid, os.WNOHANG)
    if done:
        print(os.waitstatus_to_exitcode(status))
        break
    if time.monotonic() - t0 > 120:  # only the session this harness started
        os.killpg(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        print("harness-timeout")
        break
PY
)
  verdict "$case" "$rc" 20 interrupted "$(ls "$dir"/fake-*/result.json 2>/dev/null | head -1)" \
    'r["runner"]["interrupted_by"] == "SIGINT" and r["runner"]["terminal"]["name"] == "CANCELED" and "stop_confirmed_sim" in r["runner"]' "$t0"
}

echo "=== test_runner_fake.sh $(date -Is) ROS_DOMAIN_ID=$ROS_DOMAIN_ID repo=$REPO ==="
start isaac tests/ros_fake/fake_isaac.py --duration 600
sleep 1.5
start nav2-succeed tests/ros_fake/fake_nav2.py --mode succeed --duration 2
check succeed 11 completed 'r["runner"]["terminal"]["name"] == "SUCCEEDED" and r["runner"]["states"][-1]["state"] == "DONE" and r["runner"]["stop_confirmed_sim"] - r["runner"]["terminal_sim"] >= 0.99 and r["safety_status"] == "unknown"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-abort tests/ros_fake/fake_nav2.py --mode abort --duration 2
check abort 10 completed 'r["runner"]["terminal"]["name"] == "ABORTED" and r["runner"]["terminal"]["error_code"] == 208 and r["task_outcome"] == "unknown"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-never tests/ros_fake/fake_nav2.py --mode never
check nav_timeout 10 completed 'r["task_outcome"] == "timeout" and r["runner"]["timeout_reason"] == "nav_wall_timeout" and r["runner"]["terminal"]["name"] == "CANCELED"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-reject tests/ros_fake/fake_nav2.py --mode reject
check reject 10 completed 'any(s["reason"] == "goal rejected" for s in r["runner"]["states"]) and r["task_outcome"] == "unknown"'
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
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-param-ok tests/ros_fake/fake_nav2.py --mode succeed --duration 2 --param FollowPath.max_vel_x=0.4
SCEN=fake_slow check param_in_effect 11 completed 'r["runner"]["nav2_params"]["changes"][0]["in_effect"] == 0.4 and r["runner"]["terminal"]["name"] == "SUCCEEDED"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-param-bad tests/ros_fake/fake_nav2.py --mode succeed --duration 2 --param FollowPath.max_vel_x=0.8
SCEN=fake_slow check param_not_in_effect 30 error 'any("not in effect" in e for e in r["runner"]["errors"]) and "goal_id" not in r["runner"]'
stop_all
# review round 2: a sent goal is always resolved (runner-1, runner-3) and a terminal Ctrl-C reaches the runner (runner-2)
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-late tests/ros_fake/fake_nav2.py --mode never --accept-delay 7
check accept_late 30 error 'r["runner"]["errors"] == ["accept_timeout"] and r["runner"]["safety_net"] == {"cancel": "confirmed", "stop": "confirmed"} and r["runner"]["terminal"]["name"] == "CANCELED" and not r["runner"]["abort_batch"]'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-fault tests/ros_fake/fake_nav2.py --mode never
EXTRA="--test-fault executing" check internal_error 30 error 'any("internal error" in e for e in r["runner"]["errors"]) and r["runner"]["safety_net"] == {"cancel": "confirmed", "stop": "confirmed"} and r["runner"]["terminal"]["name"] == "CANCELED"'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-fault-ignore tests/ros_fake/fake_nav2.py --mode ignore-cancel
EXTRA="--test-fault executing" check internal_error_ignored 31 error 'r["runner"]["abort_batch"] and r["runner"]["safety_net"] == {"cancel": "not confirmed"}'
stop_all
start isaac tests/ros_fake/fake_isaac.py --duration 600; sleep 1.5
start nav2-pty tests/ros_fake/fake_nav2.py --mode never
pty_check
stop_all
echo "=== result: $([[ $FAILS -eq 0 ]] && echo PASS || echo "FAIL ($FAILS)") ==="
[[ $FAILS -eq 0 ]]
