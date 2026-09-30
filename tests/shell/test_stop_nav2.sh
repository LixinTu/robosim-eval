#!/usr/bin/env bash
# start_nav2.sh / stop_nav2.sh:
#   shell-5 / codex-b-6  after `ros2 launch` died and its wrapper exited, stop_nav2.sh still stops the leftovers of this
#                        launch (proven by the ownership token every launched process inherits and their start times)
#                        and refuses, with an accurate reason, leftovers it cannot prove;
#   codex-b-8            the SIGKILL escalation spares the wrapper, so the launch's real exit status is still recorded;
#                        a missing exit status is exit 4, not 0;
#   plus the existing refusals (foreign session) and a failed process query (exit 3, nothing signalled).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

BOOT=11111111-2222-3333-4444-555555555555
TOKEN=tok-launch-1
W=5100001; L=5200001; N=5200002; N2=5200003
# launch_run <run_dir> [launch dies_on JSON] [meta extra]: a running launch of <run_dir> (wrapper W, launch L, node N).
launch_run() {
  RUN="$1"; local dies="${2-\"INT\", \"TERM\"}"
  mkdir -p "$RUN"; echo "$W" > "$RUN/nav2.pid"; : > "$RUN/nav2-launch.log"
  printf 'start_wall=2026-09-30T00:00:00\nsession=%s launch_pid=%s launch_starttime=1001 boot_id=%s wrapper_starttime=1000 token=%s\n' \
    "$W" "$L" "$BOOT" "$TOKEN" > "$RUN/nav2-launch.meta"
  mkproc "$L" "$W" "$W" 1001 "{\"argv\": [\"/usr/bin/python3\", \"/opt/ros/jazzy/bin/ros2\", \"launch\", \"carter_navigation\", \"carter_navigation.launch.xml\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"dies_on\": [$dies], \"exit_on\": {\"INT\": 1}}"
  mkproc "$N" "$W" "$L" 1005 "{\"argv\": [\"/opt/ros/jazzy/lib/nav2_controller/controller_server\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"follows\": [$L]}"
  mkproc "$W" "$W" 1 1000 "{\"argv\": [\"bash\", \"-c\", \"wrapper\", \"$RUN/nav2.pid\", \"$RUN/nav2.exit\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"follows\": [$L], \"on_exit\": [[\"$RUN/nav2.exit\", \"{status:$L}\"]]}"
}
stopnav() { bash "$R/scripts/wsl/stop_nav2.sh" "$RUN" > "$T/out.txt" 2>&1; RC=$?; }
fresh() { t_new stop_nav2.sh; cd "$T" || exit 1; : > "$T/ros2/nodes"; }

# A. the normal stop: SIGINT to the launch only; its exit code (1) recorded.
fresh; launch_run "$T/run"
stopnav
check "A: clean stop -> exit 0" 0 "$RC"
check_grep "A: SIGINT went to the launch process" "^kill INT $L\$" "$T/signals.log"
check_grep "A: launch exit code recorded" 'method=SIGINT\(launch\) .*launch_exit=1 ' "$RUN/nav2-launch.meta"

# B. the launch died, its wrapper wrote nav2.exit and exited, two nodes survive: they are this launch's and stopped.
fresh; launch_run "$T/run"
rm -rf "$ROBOSIM_PROC_ROOT/$L" "$ROBOSIM_PROC_ROOT/$W" "$ROBOSIM_PROC_ROOT/$N"; echo 137 > "$RUN/nav2.exit"
mkproc "$N" "$W" 1 1005 "{\"argv\": [\"controller_server\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"dies_on\": [\"INT\"]}"
mkproc "$N2" "$W" 1 1006 "{\"argv\": [\"rviz2\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"dies_on\": [\"INT\"]}"
stopnav
check "B: leftovers of this launch stopped -> exit 0" 0 "$RC"
check_grep "B: SIGINT to the session" "^pkill INT session $W" "$T/signals.log"
check "B: no leftover process" no "$(alive_fake "$N" || alive_fake "$N2" && echo yes || echo no)"
check_grep "B: says the wrapper had exited" 'wrapper .*exited' "$T/out.txt"
check_grep "B: launch exit code from nav2.exit kept" 'launch_exit=137' "$RUN/nav2-launch.meta"

# C. leftovers without this launch's token: refused with the real reason, not a start-time mismatch.
fresh; launch_run "$T/run"
rm -rf "$ROBOSIM_PROC_ROOT/$L" "$ROBOSIM_PROC_ROOT/$W" "$ROBOSIM_PROC_ROOT/$N"
mkproc "$N" "$W" 1 1005 '{"argv": ["something"], "env": {}, "dies_on": ["INT"]}'
stopnav
check "C: unprovable leftovers -> exit 5" 5 "$RC"
check "C: nothing signalled" 0 "$(grep -c . "$T/signals.log")"
check_grep "C: the refusal says the wrapper exited" 'wrapper .*exited' "$T/out.txt"
check_no_grep "C: not reported as a start-time mismatch" 'start time differs' "$T/out.txt"

# D. launch ignores SIGINT and SIGTERM: SIGKILL spares the wrapper, which records 137 (codex-b-8).
fresh; launch_run "$T/run" ""
stopnav
check "D: forced stop without leftovers -> exit 0" 0 "$RC"
check "D: the wrapper recorded the launch's real status" 137 "$(cat "$RUN/nav2.exit" 2>/dev/null)"
check_grep "D: SIGKILL went to the launch" "^kill KILL $L\$" "$T/signals.log"
check_no_grep "D: the wrapper was not killed" "^pkill KILL|^kill KILL $W" "$T/signals.log"
check_grep "D: method records the escalation" 'method=SIGINT\(launch\)\+SIGTERM\+SIGKILL .*launch_exit=137' "$RUN/nav2-launch.meta"

# E. everything already gone but no exit code recorded (the wrapper was killed): exit 4, not 0.
fresh; launch_run "$T/run"; fake_clear
stopnav
check "E: launch exit code unknown -> exit 4" 4 "$RC"

# F. the recorded id now leads another session (different start time): refused, nothing signalled.
fresh; launch_run "$T/run"; fake_clear
mkproc "$W" "$W" 1 77777 '{"argv": ["sshd"], "env": {}}'
stopnav
check "F: foreign session -> exit 5" 5 "$RC"
check "F: nothing signalled" 0 "$(grep -c . "$T/signals.log")"

# G. the process query fails: unknown, nothing signalled, exit 3.
fresh; launch_run "$T/run"
FAKE_PGREP_FAIL=$W stopnav
check "G: failed session query -> exit 3" 3 "$RC"
check "G: nothing signalled" 0 "$(grep -c . "$T/signals.log")"

# H. a launch started before the token existed (meta without token=) is still stopped when the wrapper matches.
fresh; launch_run "$T/run"; sed -i 's/ token=[^ ]*//' "$RUN/nav2-launch.meta"
stopnav
check "H: tokenless meta, matching wrapper -> exit 0" 0 "$RC"

# L. environments and a command line longer than a pipe buffer, token and exit file near the start: still this run's
#    launch (shell-rev-1: a `tr | grep -q` check under pipefail failed when tr died of SIGPIPE).
fresh; launch_run "$T/run"; pad_proc "$W" environ 1024
stopnav
check "L1: a large wrapper environment -> accepted, exit 0" 0 "$RC"
check_grep "L1: SIGINT went to the launch process" "^kill INT $L\$" "$T/signals.log"
fresh; launch_run "$T/run"; pad_proc "$W" cmdline 1024
stopnav
check "L2: a large wrapper command line -> accepted, exit 0" 0 "$RC"
fresh; launch_run "$T/run"
rm -rf "$ROBOSIM_PROC_ROOT/$L" "$ROBOSIM_PROC_ROOT/$W" "$ROBOSIM_PROC_ROOT/$N"; echo 137 > "$RUN/nav2.exit"
mkproc "$N" "$W" 1 1005 "{\"argv\": [\"controller_server\"], \"env\": {\"ROBOSIM_OWNER_TOKEN\": \"$TOKEN\"}, \"dies_on\": [\"INT\"]}"
pad_proc "$N" environ 1024
stopnav
check "L3: leftovers with a large environment are this launch's -> exit 0" 0 "$RC"
check_grep "L3: SIGINT to the session" "^pkill INT session $W" "$T/signals.log"

# S. start_nav2.sh records the token (inherited by the launch) and stop_nav2.sh accepts that launch.
t_new start_nav2.sh stop_nav2.sh; cd "$T" || exit 1; : > "$T/ros2/nodes"
mkdir -p "$T/prefix/share/carter_navigation/maps"
printf 'image: m.png\nresolution: 0.1\norigin: [0.0, 0.0, 0.0]\n' > "$T/prefix/share/carter_navigation/maps/carter_warehouse_navigation.yaml"
echo png > "$T/prefix/share/carter_navigation/maps/m.png"; echo "$T/prefix" > "$T/ros2/prefix"
FAKE_SPAWN=nav2 bash "$R/scripts/wsl/start_nav2.sh" "$T/srun" > "$T/start.txt" 2>&1
check "S: start_nav2 -> exit 0" 0 $?
tok=$(sed -n -E 's/^(.* )?token=([^ ]*).*/\2/p' "$T/srun/nav2-launch.meta" | tail -1)
check "S: token recorded" yes "$([[ -n "$tok" ]] && echo yes || echo no)"
lp=$(sed -n -E 's/^(.* )?launch_pid=([^ ]*).*/\2/p' "$T/srun/nav2-launch.meta" | tail -1)
check "S: the launch carries the token" yes "$(grep -qzxF "ROBOSIM_OWNER_TOKEN=$tok" "$ROBOSIM_PROC_ROOT/$lp/environ" && echo yes || echo no)"
check_grep "S: launch start time recorded" 'launch_starttime=[0-9]+' "$T/srun/nav2-launch.meta"
RUN="$T/srun"; stopnav
check "S: stop_nav2 accepts start_nav2's launch -> exit 0" 0 "$RC"
t_done
