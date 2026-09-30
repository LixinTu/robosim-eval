#!/usr/bin/env bash
# record_d0.sh:
#   shell-3 / codex-b-1  records what stop_record.sh needs to prove ownership: boot_id, a per-attempt token in every
#                        recorder's environment, each wrapper's start time; the wrappers' command lines name the attempt;
#   codex-b-4            a second record_d0.sh on the same attempt dir is refused before anything is overwritten;
#   codex-b-5 / shell-4  a recorder that is not running or not registered makes record_d0.sh stop everything it started
#                        (through stop_record.sh) before exiting 1; the launcher pid stands in for a missing pid file;
#   codex-b-3            each text stream's wrapper saves the recorder's and the line stamper's status (whole PIPESTATUS).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NAMES=(bag odom amcl_pose cmd_vel action_status tf_map_base)
setup() {
  t_new record_d0.sh stop_record.sh; cd "$T" || exit 1
  export HOME="$T/home" FAKE_SPAWN=recorder FAKE_EXIT_bag=0 FAKE_EXIT_tf_map_base=0
  unset FAKE_NOPID FAKE_DEAD FAKE_STAMP_FAIL
  printf '%s\n' "Topic information: Topic: /clock | Type: x | Count: 10 | Serialization Format: cdr" \
    "Topic: /chassis/odom | Type: x | Count: 10 | Serialization Format: cdr" "Topic: /tf | Type: x | Count: 10 |" > "$T/ros2/baginfo"
}
rec() { bash "$R/scripts/wsl/record_d0.sh" "$A" 60 > "$T/rec.txt" 2>&1; RC=$?; }
meta_of() { sed -n -E "s/^(.* )?$1=([^ ]*).*/\2/p" "$A/record.meta" | tail -1; }
alive_count() { ls -d "$ROBOSIM_PROC_ROOT"/[0-9]* 2>/dev/null | wc -l; }

# 1. normal start: ownership record complete, nothing signalled; stop_record.sh accepts all six as ours.
setup; A="$T/att"
rec
check "1: all six recorders running -> exit 0" 0 "$RC"
check "1: six registrations" 6 "$(wc -l < "$A/record.pids")"
check "1: every registration is '<name> <session> <start time> <plain|pipe>'" 6 "$(grep -cE '^[a-z_]+ [0-9]+ [0-9]+ (plain|pipe)$' "$A/record.pids")"
check "1: boot_id recorded" "$(cat "$ROBOSIM_PROC_ROOT/sys/kernel/random/boot_id")" "$(meta_of boot_id)"
TOKEN=$(meta_of token)
check "1: ownership token recorded" yes "$([[ -n "$TOKEN" ]] && echo yes || echo no)"
ok=0; while read -r name sid start kind; do
  tr '\0' '\n' < "$ROBOSIM_PROC_ROOT/$sid/environ" | grep -qxF "ROBOSIM_OWNER_TOKEN=$TOKEN" && \
  tr '\0' ' ' < "$ROBOSIM_PROC_ROOT/$sid/cmdline" | grep -qF "$A/$name.exit" && ok=$((ok + 1))
done < "$A/record.pids"
check "1: each wrapper carries the token and names its exit file" 6 "$ok"
check "1: no signal sent while starting" 0 "$(grep -c . "$T/signals.log")"
for n in "${NAMES[@]:1}"; do printf 'line\n' > "$A/$n.txt"; done; mkdir -p "$(cat "$A/bag-path.txt")"
bash "$R/scripts/wsl/stop_record.sh" "$A" > "$T/stop.txt" 2>&1
check "1: stop_record.sh confirms and stops all six -> exit 0" 0 $?
check "1: ... with one SIGINT per session" 6 "$(grep -c '^pkill INT session' "$T/signals.log")"

# 2. re-entry on the same attempt dir is refused before anything is overwritten (codex-b-4).
cp "$A/record.pids" "$T/pids.before"; cp "$A/bag-path.txt" "$T/bag.before"
setsids=$(grep -c '^setsid' "$T/calls.log")
rec
check "2: second record_d0.sh on the same attempt dir -> exit 3" 3 "$RC"
check "2: no recorder started again" "$setsids" "$(grep -c '^setsid' "$T/calls.log")"
check "2: registrations untouched" same "$(cmp -s "$A/record.pids" "$T/pids.before" && echo same || echo changed)"
check "2: bag path untouched" same "$(cmp -s "$A/bag-path.txt" "$T/bag.before" && echo same || echo changed)"

# 3. a wrapper that never writes its pid file: registered by its launcher pid, everything stopped, exit 1.
setup; A="$T/att3"; export FAKE_NOPID=odom
rec
check "3: missing pid file -> exit 1" 1 "$RC"
check "3: odom registered by its launcher pid, not MISSING" 1 "$(grep -cE '^odom [0-9]+ [0-9]+ pipe$' "$A/record.pids")"
check "3: all six sessions got SIGINT (via stop_record.sh)" 6 "$(grep -c '^pkill INT session' "$T/signals.log")"
check "3: nothing started here is left running" 0 "$(alive_count)"

# 4. a recorder that died at once: the five others are stopped before exit 1 (shell-4).
setup; A="$T/att4"; export FAKE_DEAD=cmd_vel
rec
check "4: a recorder not running -> exit 1" 1 "$RC"
check "4: the five running sessions got SIGINT" 5 "$(grep -c '^pkill INT session' "$T/signals.log")"
check "4: nothing started here is left running" 0 "$(alive_count)"

# 5. the real wrapper code keeps both statuses of a text stream (codex-b-3): recorder 0, stamper failing with 7.
setup; A="$T/att5"; export FAKE_SPAWN=exec FAKE_STAMP_FAIL=1
printf 'data: 1\n' > "$T/ros2/echo"
rec
for _ in $(seq 1 500); do [[ -f "$A/odom.exit" && -f "$A/tf_map_base.exit" ]] && break; "$REAL_SLEEP" 0.01; done
check "5: recorder status saved in odom.exit" 0 "$(cat "$A/odom.exit" 2>/dev/null)"
check "5: line stamper status saved in odom.stamp.exit" 7 "$(cat "$A/odom.stamp.exit" 2>/dev/null)"
check "5: the plain bag recorder has no stamper file" no "$([[ -e "$A/bag.stamp.exit" ]] && echo yes || echo no)"
t_done
