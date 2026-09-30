#!/usr/bin/env bash
# stop_record.sh:
#   shell-3 / codex-b-1  signal a recorded session only when it is proven to be this attempt's recorder (boot_id,
#                        wrapper start time, command line, ownership token); otherwise do not signal it, exit 7;
#   codex-b-2            check every recorder's and line stamper's real exit code, not only that the file exists;
#   codex-b-5            a MISSING registration or a failed process query is "may still be running": no bag copy.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

BOOT=11111111-2222-3333-4444-555555555555
TOKEN=tok-attempt-1
NEXT_CHILD=5200001

# attempt <dir>: a finished attempt dir as record_d0.sh leaves it (owner line, bag, text streams, goal transcript).
attempt() {
  A="$1"; mkdir -p "$A" "$T/bag"; NEXT_CHILD=5200001
  : > "$A/record.pids"
  printf 'record start 2026-09-30T00:00:00 attempt=%s max=480s bag=%s\nowner boot_id=%s token=%s\n' "$A" "$T/bag" "$BOOT" "$TOKEN" > "$A/record.meta"
  echo "$T/bag" > "$A/bag-path.txt"
  echo "bagdata" > "$T/bag/data.mcap"
  local f; for f in odom amcl_pose cmd_vel action_status tf_map_base; do printf 'l1\nl2\n' > "$A/$f.txt"; done
  echo "send_goal start x=1 y=2 yaw=0" > "$A/goal-000000.txt"
}
# session <name> <sid> <start> <kind plain|pipe> [key=value...]: a live recorder session of attempt $A in the fake
# /proc, registered in record.pids. Keys: exit=<recorder status on SIGINT> (2), dies=<signals ending it> (INT,TERM),
# stamp=<stamper status> (0), token=<env token> ($TOKEN), exitpath=<file in the wrapper command line>, register=no.
session() {
  local name=$1 sid=$2 start=$3 kind=$4; shift 4
  local exit=2 dies='"INT","TERM"' stamp=0 token=$TOKEN exitpath="$A/$name.exit" register=yes kv
  for kv in "$@"; do case $kv in exit=*) exit=${kv#*=};; dies=*) dies=${kv#*=};; stamp=*) stamp=${kv#*=};;
    token=*) token=${kv#*=};; exitpath=*) exitpath=${kv#*=};; register=*) register=${kv#*=};; esac; done
  local rec=$NEXT_CHILD; NEXT_CHILD=$((NEXT_CHILD + 1))
  local follows="[$rec]" onexit="[\"$A/$name.exit\", \"{status:$rec}\"]"
  mkproc "$rec" "$sid" "$sid" $((start + 1)) "{\"argv\": [\"timeout\", \"-s\", \"INT\", \"480\", \"ros2\", \"$name\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$token\"}, \"dies_on\": [$dies], \"exit_on\": {\"INT\": $exit}}"
  if [[ $kind == pipe ]]; then
    local st=$NEXT_CHILD; NEXT_CHILD=$((NEXT_CHILD + 1))
    mkproc "$st" "$sid" "$sid" $((start + 1)) "{\"argv\": [\"python3\", \"-u\", \"-c\", \"stamp\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$token\"}, \"follows\": [$rec], \"status\": $stamp}"
    follows="[$rec, $st]"; onexit="$onexit, [\"$A/$name.stamp.exit\", \"{status:$st}\"]"
  fi
  mkproc "$sid" "$sid" 1 "$start" "{\"argv\": [\"bash\", \"-c\", \"wrapper\", \"$A/pid-$name\", \"$exitpath\", \"timeout\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$token\"}, \"follows\": $follows, \"on_exit\": [$onexit]}"
  [[ $register == yes ]] && echo "$name $sid $start $kind" >> "$A/record.pids"
  return 0
}
six_sessions() { # the six recorders of record_d0.sh, all alive and ours
  session bag 5100001 1000 plain exit=0
  session odom 5100002 1010 pipe; session amcl_pose 5100003 1020 pipe; session cmd_vel 5100004 1030 pipe
  session action_status 5100005 1040 pipe; session tf_map_base 5100006 1050 pipe exit=0
}
baginfo() {
  printf '%s\n' "Duration: 10.0s" "Messages: 300" \
    "Topic information: Topic: /clock | Type: rosgraph_msgs/msg/Clock | Count: 100 | Serialization Format: cdr" \
    "                   Topic: /chassis/odom | Type: nav_msgs/msg/Odometry | Count: 50 | Serialization Format: cdr" \
    "                   Topic: /tf | Type: tf2_msgs/msg/TFMessage | Count: 50 | Serialization Format: cdr" \
    "                   Topic: /navigate_to_pose/_action/status | Type: x | Count: 3 | Serialization Format: cdr" \
    "                   Topic: /navigate_to_pose/_action/feedback | Type: x | Count: 90 | Serialization Format: cdr" > "$T/ros2/baginfo"
}
stop() { bash "$R/scripts/wsl/stop_record.sh" "$A" > "$T/out.txt" 2>&1; RC=$?; }
copied() { [[ -f "$A/rosbag/data.mcap" ]] && echo yes || echo no; }

# A. all six ours and alive: SIGINT to each session, clean exit codes, bag copied, exit 0.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
stop
check "A: own sessions stopped cleanly -> exit 0" 0 "$RC"
check "A: SIGINT sent to all six sessions" 6 "$(grep -c '^pkill INT session' "$T/signals.log")"
check_no_grep "A: no escalation needed" 'pkill (TERM|KILL)' "$T/signals.log"
check "A: bag copied" yes "$(copied)"

# B. the id of one recorder now leads a foreign session (other start time, no token): never signalled, exit 7.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
echo 124 > "$A/cmd_vel.exit"; echo 0 > "$A/cmd_vel.stamp.exit"   # our cmd_vel recorder ended at the cap earlier
rm -rf "$ROBOSIM_PROC_ROOT"/5100004 "$ROBOSIM_PROC_ROOT"/5200006 "$ROBOSIM_PROC_ROOT"/5200007
mkproc 5100004 5100004 1 99999 '{"argv": ["sshd", "-D"], "env": {}}'
mkproc 5300001 5100004 5100004 99999 '{"argv": ["sshd", "child"], "env": {}}'
stop
check "B: foreign session -> exit 7" 7 "$RC"
check_no_grep "B: the foreign session is never signalled" 'session 5100004' "$T/signals.log"
check "B: the foreign processes are untouched" yes "$(alive_fake 5100004 && alive_fake 5300001 && echo yes || echo no)"
check_grep "B: the refusal says why" "not this attempt's cmd_vel" "$T/out.txt"
check "B: our five other sessions were still stopped" 5 "$(grep -c '^pkill INT session' "$T/signals.log")"
check "B: our recorder was provably gone, so the bag is copied" yes "$(copied)"

# C. boot_id differs (WSL restarted): whatever holds these ids now is not ours; nothing is signalled.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
echo "99999999-0000-0000-0000-000000000000" > "$ROBOSIM_PROC_ROOT/sys/kernel/random/boot_id"
stop
check "C: other boot -> exit 7" 7 "$RC"
check "C: nothing signalled" 0 "$(grep -c . "$T/signals.log")"

# D. record.pids from before the ownership record (name + id only) with a live session: not signalled, no copy.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
sed -i 's/^\([a-z_]*\) \([0-9]*\) .*/\1 \2/' "$A/record.pids"; sed -i '/^owner /d' "$A/record.meta"
stop
check "D: unconfirmable legacy sessions -> exit 7" 7 "$RC"
check "D: nothing signalled" 0 "$(grep -c . "$T/signals.log")"
check "D: bag not copied while recorders may still run" no "$(copied)"

# E. a MISSING registration, or a failed process query, blocks the copy (codex-b-5).
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
sed -i 's/^bag .*/bag MISSING/' "$A/record.pids"
stop
check "E1: MISSING registration -> exit 7" 7 "$RC"
check "E1: bag not copied" no "$(copied)"
check_grep "E1: says the bag was not copied" 'bag not copied' "$T/out.txt"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
FAKE_PGREP_FAIL=5100001 stop
check "E2: pgrep query error -> exit 7 (not treated as 'no process')" 7 "$RC"
check "E2: bag not copied" no "$(copied)"

# F. exit codes (codex-b-2).
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100002 "$ROBOSIM_PROC_ROOT"/5200002 "$ROBOSIM_PROC_ROOT"/5200003
session odom 5100002 1010 pipe exit=1 register=no
stop
check "F1: a recorder exiting 1 on SIGINT -> exit 8" 8 "$RC"
check_grep "F1: names the recorder" 'odom.*abnormal' "$T/out.txt"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100002 "$ROBOSIM_PROC_ROOT"/5200002 "$ROBOSIM_PROC_ROOT"/5200003
session odom 5100002 1010 pipe stamp=1 register=no
stop
check "F2: a line stamper exiting 1 -> exit 8" 8 "$RC"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100003 "$ROBOSIM_PROC_ROOT"/5200004 "$ROBOSIM_PROC_ROOT"/5200005
echo 2 > "$A/amcl_pose.exit"; echo 0 > "$A/amcl_pose.stamp.exit"
stop
check "F3: a recorder that ended before the stop with exit 2 (not the cap) -> exit 8" 8 "$RC"
check_grep "F3: reported as ended before the stop" 'amcl_pose.*before the stop' "$T/out.txt"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100003 "$ROBOSIM_PROC_ROOT"/5200004 "$ROBOSIM_PROC_ROOT"/5200005
echo 124 > "$A/amcl_pose.exit"; echo 0 > "$A/amcl_pose.stamp.exit"
stop
check "F4: a recorder that ended at the time cap (124) is accepted -> exit 0" 0 "$RC"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100003 "$ROBOSIM_PROC_ROOT"/5200004 "$ROBOSIM_PROC_ROOT"/5200005
: > "$A/amcl_pose.exit"; echo 0 > "$A/amcl_pose.stamp.exit"
stop
check "F5: a blank exit-code file -> exit 8" 8 "$RC"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100003 "$ROBOSIM_PROC_ROOT"/5200004 "$ROBOSIM_PROC_ROOT"/5200005
echo 124 > "$A/amcl_pose.exit"
stop
check "F6: a text stream without its stamper exit file -> exit 4" 4 "$RC"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100002 "$ROBOSIM_PROC_ROOT"/5200002 "$ROBOSIM_PROC_ROOT"/5200003
session odom 5100002 1010 pipe dies='"TERM"' exit=2 register=no
stop
check "F7: a recorder needing SIGTERM -> exit 8 (abnormal end, status 143)" 8 "$RC"
check "F7: SIGTERM went only to that session" "pkill TERM session 5100002" "$(grep '^pkill TERM' "$T/signals.log" | cut -d' ' -f1-4)"

t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
stop
check "F8: first stop of the attempt -> exit 0" 0 "$RC"
stop
check "F8: stopping it again (all gone, stopped by the earlier request) -> exit 0" 0 "$RC"
check_grep "F8: says an earlier stop request ended them" 'earlier stop' "$T/out.txt"

# G. the wrapper exited but recorder processes remain in its session.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100002
stop
check_grep "G1: leftovers carrying the token are ours and signalled" '^pkill INT session 5100002' "$T/signals.log"
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100002 "$ROBOSIM_PROC_ROOT"/5200002 "$ROBOSIM_PROC_ROOT"/5200003
mkproc 5300002 5100002 5100002 5000 '{"argv": ["something"], "env": {}}'
stop
check "G2: leftovers without the token -> exit 7" 7 "$RC"
check_no_grep "G2: not signalled" 'session 5100002' "$T/signals.log"
check "G2: bag not copied (cannot tell whether a recorder still runs)" no "$(copied)"

# H. required text stream empty.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
: > "$A/odom.txt"
stop
check "H: empty odom.txt -> exit 6" 6 "$RC"

# I. a wrapper that has not reached setsid yet (its session id has no members) is still found and signalled.
t_new stop_record.sh; cd "$T" || exit 1; baginfo
attempt "$T/att"; six_sessions
rm -rf "$ROBOSIM_PROC_ROOT"/5100001 "$ROBOSIM_PROC_ROOT"/5200001
mkproc 5100001 4000000 3999999 1000 "{\"argv\": [\"setsid\", \"nohup\", \"bash\", \"-c\", \"wrapper\", \"$A/pid-bag\", \"$A/bag.exit\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"dies_on\": [\"INT\"]}"
stop
check_grep "I: the pre-setsid wrapper gets the signal directly" '^kill INT 5100001' "$T/signals.log"
t_done
