#!/usr/bin/env bash
# Offline scans over the real run directories under artifacts/ (no Isaac needed): the first /plan direction vs the
# AMCL heading and the first /cmd_vel (plan_heading.py, reads the rosbags kept on this machine), and the length of the
# minimum-rotation phase at the start of /cmd_vel (cmd_vel_scan.py, reads cmd_vel.txt).
# Both halves cover the same run directories, found at any depth: every directory named <scenario>-2026093*-* that
# holds a cmd_vel.txt (cmd_vel_scan.py's own rule; D0 attempt-NN directories and fake-node runs are not included).
# plan_heading.py reports a run without a kept rosbag/ as "no bag". Each half prints how many runs it covers.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"   # the checkout this script is in
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full >/dev/null || exit 2
set -u
A="$REPO/artifacts"
mapfile -t RUNS < <(find "$A" -type f -name cmd_vel.txt -printf '%h\n' | sort | while read -r d; do
  if [[ "$(basename "$d")" == *-2026093*-* ]]; then echo "$d"; fi; done)
echo "plan_heading.py: ${#RUNS[@]} run dirs under $A"
python3 "$HERE/plan_heading.py" "${RUNS[@]}" 2>&1 | grep -v '^\[INFO\]'
echo "---"
SCAN="$(python3 "$HERE/cmd_vel_scan.py")"
rc=$?
printf '%s\n' "$SCAN"
echo "cmd_vel_scan.py: $(printf '%s\n' "$SCAN" | tail -n +2 | grep -c ' | ') rows (its own search, same rule)"
exit "$rc"
