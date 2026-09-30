#!/usr/bin/env bash
# watch_clock.sh — RoboSim Eval D0c: record wall time against simulation time (/clock) as a continuous stream.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/watch_clock.sh <seconds> <out_file>
# Used for the pause/resume test (plan doc B7 step 3): while this runs, the user presses Pause and later Play in
# Isaac Sim. A pause shows up as a gap in the stream (no /clock messages) with equal sim time before and after it.
# Output lines: <wall time ISO with ns> <sim seconds as float>. Exit code 124 from timeout = full window, by design.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
SECS="${1:-90}"; OUT="${2:-$REPO/artifacts/d0c/clock-watch.txt}"
mkdir -p "$(dirname "$OUT")"
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
{
echo "# watch_clock.sh start $(date -Is) duration=${SECS}s (continuous /clock stream)"
timeout "$SECS" ros2 topic echo /clock --field clock 2>&1 | python3 -u -c '
import sys, time, datetime
sec = None
for line in sys.stdin:
    line = line.strip()
    if line.startswith("sec:"):
        sec = int(line.split(":")[1])
    elif line.startswith("nanosec:") and sec is not None:
        ns = int(line.split(":")[1])
        print(datetime.datetime.now().isoformat(timespec="milliseconds"), f"{sec + ns/1e9:.3f}")
        sec = None
'
echo "# watch_clock.sh end $(date -Is) timeout_exit=${PIPESTATUS[0]}"
} > "$OUT" 2>&1
echo "written $OUT ($(wc -l < "$OUT") lines)"
