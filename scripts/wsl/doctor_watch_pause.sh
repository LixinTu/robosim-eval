#!/usr/bin/env bash
# doctor_watch_pause.sh - RoboSim Eval D1 acceptance helper: capture one doctor run while the user has Isaac paused and
# one after the user resumes, without a back-and-forth. The user only presses Pause in Isaac, waits a few seconds, and
# presses Play again.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor_watch_pause.sh <out_dir> [<deadline_s>]
# Loop: run the doctor.sh next to this script (short 3 s window) until it exits 10 (simulation not advancing) and keep
# that run as paused/; then run it until it exits 0 again and keep that run as resumed/. Every intermediate run is
# logged in watch.log with its exit code. Gives up after <deadline_s> seconds of wall time (default 1200).
# Exit: 0 both runs captured; 3 deadline reached before the pause or the resume was seen; 2 setup failure.
set -uo pipefail
OUT="${1:?out dir}"; DEADLINE_S="${2:-1200}"
DOCTOR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/doctor.sh" || exit 2   # the doctor.sh of this checkout
mkdir -p "$OUT" || exit 2
LOG="$OUT/watch.log"
END=$(( $(date +%s) + DEADLINE_S ))
echo "doctor_watch_pause.sh start $(date -Is) deadline=${DEADLINE_S}s doctor=$DOCTOR" | tee "$LOG"

wait_for() {  # wait_for <wanted exit code> <keep dir>; returns 0 when captured, 3 on deadline
  local want="$1" keep="$2" n=0 rc
  while [[ $(date +%s) -lt $END ]]; do
    n=$((n + 1))
    rm -rf "$OUT/.try"
    bash "$DOCTOR" --window 3 --out "$OUT/.try" > "$OUT/.try.txt" 2>&1
    rc=$?
    echo "$(date -Is) try $n: doctor exit $rc ($(grep -m1 '^verdict:' "$OUT/.try.txt"))" | tee -a "$LOG"
    if [[ "$rc" == "$want" ]]; then
      mkdir -p "$OUT/$keep" && mv "$OUT/.try.txt" "$OUT/$keep/doctor.txt" && mv "$OUT/.try"/*.json "$OUT/$keep/" 2>/dev/null
      rm -rf "$OUT/.try"
      echo "$(date -Is) captured $keep (exit $rc)" | tee -a "$LOG"
      return 0
    fi
    sleep 1
  done
  return 3
}

wait_for 10 paused || { echo "$(date -Is) deadline: no pause seen" | tee -a "$LOG"; exit 3; }
wait_for 0 resumed || { echo "$(date -Is) deadline: no resume seen" | tee -a "$LOG"; exit 3; }
rm -f "$OUT/.try.txt"
echo "doctor_watch_pause.sh end $(date -Is): paused and resumed runs captured" | tee -a "$LOG"
