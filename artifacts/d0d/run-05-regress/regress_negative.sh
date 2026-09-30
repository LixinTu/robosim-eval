#!/usr/bin/env bash
# Negative-path regression for the D0 scripts (run inside WSL). Each case prints its expected and actual exit code.
set -uo pipefail
S=/mnt/d/RoboSim-Eval/scripts/wsl
R=/mnt/d/RoboSim-Eval/artifacts/d0d/run-05-regress
A=/mnt/d/RoboSim-Eval/artifacts/d0d/run-01/attempt-01
check() { local name="$1" want="$2" got="$3"; printf '%-58s expected %-8s got %-4s %s\n' "$name" "$want" "$got" "$([[ " $want " == *" $got "* ]] && echo PASS || echo FAIL)"; }

bash -l $S/send_goal.sh $R/neg-goal -4.0 -1.0 pi > $R/neg-send_goal-yaw.txt 2>&1; check "send_goal: non-numeric yaw" 2 $?

H0=$(sha256sum $A/result.json | cut -d' ' -f1)
bash -l $S/analyze_attempt.sh $A --goal -3.0 -1.0 0.0 --spawn -6.0 -1.0 3.141592653589793 > $R/neg-analyze-goal-mismatch.txt 2>&1; rc=$?
H1=$(sha256sum $A/result.json | cut -d' ' -f1)
check "analyze: --goal differs from the sent goal" 2 $rc
check "analyze: result.json untouched on mismatch (0 = same hash)" 0 $([[ $H0 == $H1 ]] && echo 0 || echo 1)

mkdir -p $R/neg-foreign-session
setsid sleep 300 < /dev/null > /dev/null 2>&1 &
FOREIGN=$!; sleep 0.5
echo $FOREIGN > $R/neg-foreign-session/nav2.pid
echo "start_wall=fake session=$FOREIGN launch_pid=$FOREIGN boot_id=$(cat /proc/sys/kernel/random/boot_id) wrapper_starttime=1" > $R/neg-foreign-session/nav2-launch.meta
: > $R/neg-foreign-session/nav2-launch.log
bash -l $S/stop_nav2.sh $R/neg-foreign-session > $R/neg-stop_nav2-foreign.txt 2>&1; rc=$?
check "stop_nav2: refuses a session it cannot confirm" 5 $rc
check "stop_nav2: foreign session still alive (0 = alive)" 0 $(kill -0 $FOREIGN 2>/dev/null && echo 0 || echo 1)
kill $FOREIGN

mkdir -p $R/neg-bag-missing; : > $R/neg-bag-missing/record.pids; echo /home/nonexistent/bag > $R/neg-bag-missing/bag-path.txt
bash -l $S/stop_record.sh $R/neg-bag-missing > $R/neg-stop_record-bag-missing.txt 2>&1; check "stop_record: bag directory missing" 5 $?

bash -l $S/map_overview.sh $R/neg-map-overview.txt "1;2" > $R/neg-map-overview-stdout.txt 2>&1; check "map_overview: malformed candidate point" "1 2" $?

bash -l $S/check_nav2_ready.sh $R/neg-ready-without-nav2 > /dev/null 2>&1; check "check_nav2_ready: Nav2 not running -> NOT READY" 1 $?

ROBOSIM_SETUP_LOG=$R/setup-workspace-rerun.log bash -l $S/setup_workspace.sh > /dev/null 2>&1; check "setup_workspace: idempotent re-run (exit file: $(cat $R/setup-workspace-rerun.exit 2>/dev/null))" 0 $?
