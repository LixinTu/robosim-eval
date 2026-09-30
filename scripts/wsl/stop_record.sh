#!/usr/bin/env bash
# stop_record.sh — RoboSim Eval D0d: stop the recorders started by record_d0.sh, then check what was captured.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_record.sh <attempt_dir>
# Each recorder was started with setsid, so its recorded id is a session id; `timeout` creates its own process group
# inside that session, therefore the whole SESSION is signalled (pkill -s), not just one process group.
# Ownership (plan doc B0: stop only what you have confirmed you own; findings shell-3, codex-b-1): record.pids holds
# "<name> <session id> <wrapper start time> <plain|pipe>", record.meta the boot_id and this attempt's ownership token (an
# environment variable every recorder process inherits). A session is signalled only when the boot_id matches and either
# its wrapper still exists with the recorded start time (/proc/<pid>/stat field 22), a command line naming
# <attempt_dir>/<name>.exit and the token, or the wrapper has exited and every process left in the session carries the
# token and started after it. Anything else is left alone and reported (exit 7): after a WSL restart or a PID wrap the
# id may belong to someone else, and an attempt dir recorded before this check has no ownership record at all.
# Escalation: SIGINT (wait up to 20 s) -> SIGTERM (10 s) -> SIGKILL, only for sessions confirmed as ours. The bag is
# copied into <attempt_dir>/rosbag (git-ignored) only when no recorder can still be running: a session that survived
# SIGKILL, could not be confirmed, has no registered id, or could not be queried (pgrep exit >= 2) blocks the copy
# (finding codex-b-5).
# Exit codes (finding codex-b-2): <name>.exit holds the recorder's, <name>.stamp.exit the line stamper's status of a text
# stream. Accepted: 0 or 2 after the stop request (ros2 bag / ros2 topic echo return 2 = signal.SIGINT when stopped),
# 124 = the time cap was reached; a stamper must exit 0. Anything else, a non-numeric value, or a recorder that had
# already ended before the (first) stop request without reaching the cap is an abnormal end. A repeated stop of the
# same attempt (record.meta already has a "record stop" line) accepts sessions ended by the earlier request.
# Required data (plan doc A7: no data must not look like success): bag topics /clock, /chassis/odom, /tf and a non-empty
# odom.txt; when a goal transcript (goal-*.txt) exists, also the NavigateToPose status and feedback topics and a
# non-empty action_status.txt.
# Exit: 0 ok; 3 a recorder session survived SIGKILL; 4 a recorder or stamper exit-code file is missing; 5 bag missing,
#       not copied (a recorder may still run), `ros2 bag info` failed or the copy failed; 6 a required topic or text
#       stream has no data; 7 a registered session was not signalled: not confirmed as this attempt's recorder, no id
#       registered, or the process query failed; 8 a recorder or line stamper ended abnormally.
#       The first failure's code is used; every failure is printed.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
ATT="${1:?attempt dir required}"
[[ -d "$ATT" ]] || { echo "no attempt dir $ATT"; exit 1; }
ATT="$(cd "$ATT" && pwd -P)"   # the same spelling record_d0.sh used for the wrappers' command lines
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
set -u
PROC="${ROBOSIM_PROC_ROOT:-/proc}"   # test seam: tests/shell point this at a fake /proc tree
[[ -f "$ATT/record.pids" ]] || { echo "no record.pids in $ATT"; exit 1; }
RC=0
fail() { local c=$1; shift; echo "FAIL($c): $*"; [[ $RC -eq 0 ]] && RC=$c; return 0; }
meta_value() { sed -n -E "s/^(.* )?$1=([^ ]*).*/\2/p" "$ATT/record.meta" 2>/dev/null | tail -1; }
stat_field() { sed -E 's/^.*\) //' "$PROC/$1/stat" 2>/dev/null | awk -v f="$2" '{print $f}'; }   # 4 session, 20 start
has_token() { [[ -n "$TOKEN" ]] && tr '\0' '\n' < "$PROC/$1/environ" 2>/dev/null | grep -qxF "ROBOSIM_OWNER_TOKEN=$TOKEN"; }
BOOT=$(meta_value boot_id); TOKEN=$(meta_value token)
PREV_STOP=$(grep -m1 '^record stop ' "$ATT/record.meta" 2>/dev/null)   # an earlier stop_record.sh run on this attempt
NAMES=(); SIDS=(); STARTS=(); KINDS=()
while read -r name sid start kind _; do
  [[ -n "${name:-}" ]] || continue
  NAMES+=("$name"); SIDS+=("${sid:-}"); STARTS+=("${start:-}"); KINDS+=("${kind:-}")
done < "$ATT/record.pids"

# own_leader <i>: the wrapper process of recorder i still exists and is this attempt's (it may not have reached setsid
# yet, then its session has no members).
own_leader() {
  local i=$1 sid=${SIDS[$1]}
  [[ -n "$BOOT" && "$(cat "$PROC/sys/kernel/random/boot_id" 2>/dev/null)" == "$BOOT" ]] || return 1
  [[ "${STARTS[$i]}" =~ ^[0-9]+$ && "$(stat_field "$sid" 20)" == "${STARTS[$i]}" ]] || return 1
  tr '\0' ' ' < "$PROC/$sid/cmdline" 2>/dev/null | grep -qF "$ATT/${NAMES[$i]}.exit" || return 1
  has_token "$sid"
}
# classify <i>: STATE[i] = own (ours, running) | gone (nothing left) | foreign (the id now belongs to other processes, so
# ours is gone) | unknown (cannot tell: may still be running); WHY[i] says why.
classify() {
  local i=$1 sid=${SIDS[$1]} members rc p
  STATE[i]=unknown; WHY[i]=""
  if [[ ! "$sid" =~ ^[0-9]+$ ]]; then WHY[i]="no session id was registered ('$sid')"; return; fi
  members=$(pgrep -s "$sid" 2>/dev/null); rc=$?
  if [[ $rc -gt 1 ]]; then WHY[i]="the process query failed (pgrep -s exit $rc)"; return; fi
  if own_leader "$i"; then STATE[i]=own; return; fi
  if [[ $rc -eq 1 ]]; then STATE[i]=gone; return; fi
  if [[ -z "$BOOT" || -z "$TOKEN" || ! "${STARTS[$i]}" =~ ^[0-9]+$ ]]; then
    WHY[i]="no ownership record (attempt recorded before the ownership check)"; return
  fi
  if [[ "$(cat "$PROC/sys/kernel/random/boot_id" 2>/dev/null)" != "$BOOT" ]]; then
    STATE[i]=foreign; WHY[i]="boot_id differs from the recording's (WSL restarted); the id belongs to other processes now"; return
  fi
  if [[ -d "$PROC/$sid" ]]; then   # pid + start time identify a process: only a different start time proves ours is gone
    if [[ "$(stat_field "$sid" 20)" == "${STARTS[$i]}" ]]; then
      WHY[i]="process $sid has the recorded start time, but its command line or ownership token does not match"; return
    fi
    STATE[i]=foreign; WHY[i]="process $sid is not this attempt's ${NAMES[$i]} wrapper (its start time differs)"; return
  fi
  for p in $members; do
    if ! has_token "$p" || [[ "$(stat_field "$p" 20)" -lt "${STARTS[$i]}" ]]; then
      WHY[i]="its wrapper exited and process $p left in the session is not confirmed as this attempt's"; return
    fi
  done
  STATE[i]=own
}
session_alive() { # session_alive <i>: 0 when something of recorder i may still run (a failed query counts as running)
  local i=$1
  pgrep -s "${SIDS[$i]}" >/dev/null 2>&1
  [[ $? -ne 1 ]] || own_leader "$i"
}
alive_any() { local i; for i in "${!NAMES[@]}"; do [[ ${STATE[i]} == own ]] && session_alive "$i" && return 0; done; return 1; }
signal_all() {
  local sig=$1 i sid
  for i in "${!NAMES[@]}"; do
    [[ ${STATE[i]} == own ]] && session_alive "$i" || continue
    sid=${SIDS[$i]}
    pkill "-$sig" -s "$sid"
    # a wrapper that has not called setsid yet is not in its own session: signal it directly (env: the external kill)
    if [[ -d "$PROC/$sid" && "$(stat_field "$sid" 4)" != "$sid" ]] && own_leader "$i"; then env kill "-$sig" "$sid"; fi
    echo "SIG$sig -> session ${NAMES[$i]} ($sid)"
  done
}
wait_gone() { local n=$1; for _ in $(seq 1 "$n"); do alive_any || return 0; sleep 1; done; alive_any && return 1; return 0; }

declare -a STATE WHY
UNSTOPPED=()
for i in "${!NAMES[@]}"; do
  classify "$i"
  case ${STATE[i]} in
    gone) if [[ -n "$PREV_STOP" ]]; then STATE[i]=stopped; echo "session ${NAMES[$i]} (${SIDS[$i]}) ended by the earlier stop request ($PREV_STOP)"
          else echo "session ${NAMES[$i]} (${SIDS[$i]}) had already ended before the stop request"; fi ;;
    foreign) fail 7 "session ${NAMES[$i]} (${SIDS[$i]}) not signalled: ${WHY[i]}" ;;
    unknown) fail 7 "session ${NAMES[$i]} (${SIDS[$i]}) not signalled: ${WHY[i]}; it may still be running"
             UNSTOPPED+=("${NAMES[$i]}") ;;
  esac
done
signal_all INT
if ! wait_gone 20; then signal_all TERM; wait_gone 10 || { signal_all KILL; sleep 2; }; fi
for i in "${!NAMES[@]}"; do
  if [[ ${STATE[i]} == own ]] && session_alive "$i"; then
    fail 3 "session ${NAMES[$i]} (${SIDS[$i]}) still alive after SIGKILL"; UNSTOPPED+=("${NAMES[$i]}")
  fi
done
echo "record stop $(date -Is)" >> "$ATT/record.meta"

echo "recorder exit codes (0/2 = stopped by SIGINT; 124 = time cap reached; a line stamper exits 0):"
check_exit() { # check_exit <i> <file> <what>
  local i=$1 f=$2 what=$3 v
  if [[ ! -f "$f" ]]; then
    fail 4 "$(basename "$f") missing ($what did not record its exit code)"; echo "  $what exit=missing" >> "$ATT/record.meta"; return
  fi
  v=$(tr -d '[:space:]' < "$f")
  printf '  %-24s session %-8s exit=%s\n' "$what" "${SIDS[$i]}" "$v" | tee -a "$ATT/record.meta"
  if [[ ! "$v" =~ ^[0-9]+$ ]]; then fail 8 "$what: $(basename "$f") holds '$v', not an exit code"
  elif [[ "$what" == *stamper ]]; then [[ $v -eq 0 ]] || fail 8 "$what ended abnormally (exit $v): text lines may be missing"
  elif [[ $v -eq 124 ]]; then echo "  ($what reached the time cap before the stop request)"
  elif [[ ${STATE[i]} != own && ${STATE[i]} != stopped ]]; then fail 8 "$what had ended before the stop request with exit $v (not the time cap)"
  elif [[ $v -ne 0 && $v -ne 2 ]]; then fail 8 "$what ended abnormally (exit $v)"
  fi
}
for i in "${!NAMES[@]}"; do
  check_exit "$i" "$ATT/${NAMES[$i]}.exit" "${NAMES[$i]}"
  [[ ${KINDS[i]} == pipe ]] && check_exit "$i" "$ATT/${NAMES[$i]}.stamp.exit" "${NAMES[$i]} stamper"
done

BAG=$(cat "$ATT/bag-path.txt" 2>/dev/null)
if [[ ${#UNSTOPPED[@]} -gt 0 ]]; then
  fail 5 "bag not copied: recorder(s) ${UNSTOPPED[*]} may still be running"
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
lines() { if [[ -f "$ATT/$1.txt" ]]; then wc -l < "$ATT/$1.txt"; else echo 0; fi; }
for f in odom amcl_pose cmd_vel action_status tf_map_base; do printf '%-14s %6d lines\n' "$f" "$(lines "$f")"; done
REQUIRED_TXT=(odom)
if compgen -G "$ATT/goal-*.txt" >/dev/null; then REQUIRED_TXT+=(action_status); fi
for f in "${REQUIRED_TXT[@]}"; do [[ $(lines "$f") -gt 0 ]] || fail 6 "required text stream $f.txt has no lines"; done
echo "stop_record result: exit $RC"
exit $RC
