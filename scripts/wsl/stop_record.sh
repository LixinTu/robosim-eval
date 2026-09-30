#!/usr/bin/env bash
# stop_record.sh — RoboSim Eval D0d: stop the recorders started by record_d0.sh, then check what was captured.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_record.sh <attempt_dir>
# Each recorder was started with setsid, so its recorded id is a session id; `timeout` creates its own process group
# inside that session, therefore the whole SESSION is signalled (pkill -s), not just one process group.
# Escalation: SIGINT (wait up to 20 s) -> SIGTERM (10 s) -> SIGKILL. The bag is copied into <attempt_dir>/rosbag
# (git-ignored) only after every recorder session is gone, so a bag is never copied while it is still being written.
# Required topics (plan doc A7: no data must not look like success): /clock, /chassis/odom, /tf; when a goal transcript
# (goal-*.txt) exists in the attempt dir, also the NavigateToPose status and feedback topics.
# Exit: 0 ok; 3 a recorder session survived SIGKILL; 4 a recorder exit-code file is missing; 5 bag missing,
#       `ros2 bag info` failed or the copy failed; 6 a required topic has 0 messages. The first failure's code is used;
#       every failure is printed.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
ATT="${1:?attempt dir required}"
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
set -u
[[ -f "$ATT/record.pids" ]] || { echo "no record.pids in $ATT"; exit 1; }
RC=0
fail() { local c=$1; shift; echo "FAIL($c): $*"; [[ $RC -eq 0 ]] && RC=$c; return 0; }
NAMES=(); SIDS=()
while read -r name sid; do [[ -n "${sid:-}" ]] && { NAMES+=("$name"); SIDS+=("$sid"); }; done < "$ATT/record.pids"
alive_any() { local s; for s in "${SIDS[@]}"; do pgrep -s "$s" >/dev/null 2>&1 && return 0; done; return 1; }
signal_all() {
  local sig=$1 i
  for i in "${!SIDS[@]}"; do
    if pgrep -s "${SIDS[$i]}" >/dev/null 2>&1; then pkill "-$sig" -s "${SIDS[$i]}"; echo "SIG$sig -> session ${NAMES[$i]} (${SIDS[$i]})"; fi
  done
}
wait_gone() { local n=$1; for _ in $(seq 1 "$n"); do alive_any || return 0; sleep 1; done; alive_any && return 1; return 0; }

signal_all INT
if ! wait_gone 20; then signal_all TERM; wait_gone 10 || { signal_all KILL; sleep 2; }; fi
if alive_any; then
  for i in "${!SIDS[@]}"; do pgrep -s "${SIDS[$i]}" >/dev/null 2>&1 && fail 3 "session ${NAMES[$i]} (${SIDS[$i]}) still alive after SIGKILL"; done
fi
echo "record stop $(date -Is)" >> "$ATT/record.meta"

echo "recorder exit codes (124 = time cap reached; ros2 topic echo returns 2 = signal.SIGINT when stopped):"
for i in "${!NAMES[@]}"; do
  f="$ATT/${NAMES[$i]}.exit"
  if [[ -f "$f" ]]; then printf '  %-14s session %-7s exit=%s\n' "${NAMES[$i]}" "${SIDS[$i]}" "$(cat "$f")" | tee -a "$ATT/record.meta"
  else fail 4 "${NAMES[$i]}.exit missing (recorder did not record its exit code)"; echo "  ${NAMES[$i]} exit=missing" >> "$ATT/record.meta"; fi
done

BAG=$(cat "$ATT/bag-path.txt" 2>/dev/null || true)
if [[ $RC -eq 3 ]]; then
  fail 5 "bag not copied because a recorder session is still alive"
elif [[ -z "$BAG" || ! -d "$BAG" ]]; then
  fail 5 "bag directory not found (${BAG:-no bag-path.txt})"
else
  if ros2 bag info "$BAG" > "$ATT/bag-info.txt" 2>&1; then echo "bag info ok"; else fail 5 "ros2 bag info failed (see bag-info.txt)"; fi
  if mkdir -p "$ATT/rosbag" && cp -r "$BAG"/. "$ATT/rosbag/"; then echo "bag copied to $ATT/rosbag ($(du -sh "$ATT/rosbag" | cut -f1))"; else fail 5 "copying the bag failed"; fi
  grep -E 'Duration|Messages|Topic:' "$ATT/bag-info.txt" | head -20
  REQUIRED=(/clock /chassis/odom /tf)
  if compgen -G "$ATT/goal-*.txt" >/dev/null; then REQUIRED+=(/navigate_to_pose/_action/status /navigate_to_pose/_action/feedback); fi
  for t in "${REQUIRED[@]}"; do
    n=$(grep -E "Topic: $t \|" "$ATT/bag-info.txt" | sed -E 's/.*Count: ([0-9]+).*/\1/' | head -1)
    if [[ -z "$n" || "$n" -eq 0 ]]; then fail 6 "required topic $t recorded ${n:-no} messages"; fi
  done
fi
for f in odom amcl_pose cmd_vel action_status tf_map_base; do
  printf '%-14s %6d lines\n' "$f" "$(wc -l < "$ATT/$f.txt" 2>/dev/null || echo 0)"
done
echo "stop_record result: exit $RC"
exit $RC
