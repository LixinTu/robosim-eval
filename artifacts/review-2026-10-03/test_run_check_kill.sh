#!/usr/bin/env bash
# Exercise verify.sh's run_check on checks that hit their time limit: one that stops on INT (124) and one that ignores
# INT and is KILLed 10 s later (137). Usage: bash test_run_check_kill.sh <verify.sh to take run_check from> <out dir>
set -uo pipefail
SRC="$1"; OUT="$2"; mkdir -p "$OUT"
ROOT=/tmp; REC="$OUT/commands.md"; SHELL_DESC=test; FAILED=(); TOTAL=0; : > "$REC"
# shellcheck disable=SC1090
source <(sed -n '/^uptime_s()/,/^}/p' "$SRC")
run_check stops-on-int 2 'x' "" -- python3 -c 'import time; time.sleep(30)'
run_check ignores-int 2 'x' "" -- python3 -c 'import signal, time; signal.signal(signal.SIGINT, signal.SIG_IGN); time.sleep(30)'
cat "$REC"
