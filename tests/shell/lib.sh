# lib.sh — helpers for the stub-based shell-script tests (sourced by tests/shell/test_*.sh; driven by
# tests/test_shell_scripts.py). No ROS, no simulator, and no real process is ever signalled:
#   - the script under test runs as a COPY inside a temporary repository skeleton, so it sources the stub ros_env.sh and
#     dds_env.sh written next to it (the real ones would put /opt/ros/jazzy/bin first on PATH);
#   - $T/bin comes first on PATH with stubs for ros2, pgrep, pkill, kill, setsid, sleep, timeout and python3 (the last
#     only to make the line stamper fail on request);
#   - processes live in a fake /proc tree ($ROBOSIM_PROC_ROOT, see fakeproc.py) with ids above PID_MAX_LIMIT.
# Every call a stub receives is appended to $T/calls.log, every signal to $T/signals.log.
set -uo pipefail
TESTS_SHELL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_REPO="$(cd "$TESTS_SHELL/../.." && pwd)"
REAL_PY="$(command -v python3)"
REAL_SLEEP="$(command -v sleep)"
FAILS=0
T=""

# t_new <script>...: fresh temp dir $T with a repo skeleton $R holding copies of the named scripts/wsl files.
t_new() {
  [[ -n "$T" ]] && rm -rf "$T"
  T=$(mktemp -d "${TMPDIR:-/tmp}/robosim-shelltest.XXXXXX")
  R="$T/repo"
  mkdir -p "$R/scripts/wsl" "$T/bin" "$T/proc/sys/kernel/random" "$T/ros2"
  local s
  for s in "$@"; do cp "$SRC_REPO/scripts/wsl/$s" "$R/scripts/wsl/$s"; done
  [[ -f "$R/scripts/wsl/ros_env.sh" ]] || printf '%s\n' 'echo "stub ros_env.sh $*"' 'export ROS_DOMAIN_ID=199 RMW_IMPLEMENTATION=stub' 'return 0' > "$R/scripts/wsl/ros_env.sh"
  [[ -f "$R/scripts/wsl/dds_env.sh" ]] || printf '%s\n' 'echo "stub dds_env.sh"' 'export FASTRTPS_DEFAULT_PROFILES_FILE=/dev/null' 'return 0' > "$R/scripts/wsl/dds_env.sh"
  echo "11111111-2222-3333-4444-555555555555" > "$T/proc/sys/kernel/random/boot_id"
  : > "$T/calls.log"; : > "$T/signals.log"
  export ROBOSIM_PROC_ROOT="$T/proc" FAKEPROC="$TESTS_SHELL/fakeproc.py" REAL_PY REAL_SLEEP FAKE_T="$T"
  local stub
  for stub in pgrep pkill kill; do
    printf '#!/bin/bash\nexec "%s" "%s" %s "$@"\n' "$REAL_PY" "$TESTS_SHELL/fakeproc.py" "$stub" > "$T/bin/$stub"
  done
  printf '#!/bin/bash\nexec "%s" "%s" spawn "$$" "$@"\n' "$REAL_PY" "$TESTS_SHELL/fakeproc.py" > "$T/bin/setsid"
  cat > "$T/bin/sleep" <<'EOF'
#!/bin/bash
# sleep stub: no waiting, except that the caller's unfinished background jobs (the stub setsid spawns) are allowed to
# finish first (real time, at most 5 s), so the scripts' polling loops see their result deterministically.
echo "sleep $*" >> "$FAKE_T/calls.log"
for _ in $(seq 1 500); do
  busy=0
  for p in $(/usr/bin/pgrep -P "$PPID"); do
    [[ $p == "$$" ]] && continue
    st=$(sed -E 's/^.*\) //' "/proc/$p/stat" 2>/dev/null | cut -c1)
    [[ -n "$st" && "$st" != Z ]] && busy=1
  done
  [[ $busy -eq 0 ]] && break
  "$REAL_SLEEP" 0.01
done
exit "${FAKE_SLEEP_RC:-0}"
EOF
  cat > "$T/bin/timeout" <<'EOF'
#!/bin/bash
# timeout stub: logs its arguments, then runs the command without any time limit or signal.
echo "timeout $*" >> "$FAKE_T/calls.log"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|-k|--signal|--kill-after) shift 2 ;;
    --preserve-status|--foreground|-v|--verbose|--signal=*|--kill-after=*) shift ;;
    *) break ;;
  esac
done
shift  # the duration
exec "$@"
EOF
  cat > "$T/bin/python3" <<'EOF'
#!/bin/bash
# python3 stub: the real interpreter, except that the wall-clock line stamper fails when FAKE_STAMP_FAIL=1.
if [[ "${FAKE_STAMP_FAIL:-0}" == 1 && "$*" == *datetime.datetime.now* ]]; then echo "stamper: forced failure" >&2; exit 7; fi
exec "$REAL_PY" "$@"
EOF
  cat > "$T/bin/ros2" <<'EOF'
#!/bin/bash
# ros2 stub: canned answers from $FAKE_T/ros2/<file>; never talks to a ROS graph.
echo "ros2 $*" >> "$FAKE_T/calls.log"
D="$FAKE_T/ros2"
out() { [[ -f "$D/$1" ]] && cat "$D/$1"; if [[ -f "$D/$1.rc" ]]; then exit "$(cat "$D/$1.rc")"; fi; exit 0; }
case "$1 $2" in
  "pkg prefix") out prefix ;;
  "node list") out nodes ;;
  "action list") out actions ;;
  "action send_goal") out send_goal ;;
  "topic echo") out echo ;;
  "bag info") out baginfo ;;
  "bag record") out bagrecord ;;
  "run tf2_ros") out tf ;;
  *) echo "ros2 stub: unsupported: $*" >&2; exit 99 ;;
esac
EOF
  chmod +x "$T/bin/"*
  export PATH="$T/bin:$PATH"
}

# mkproc <pid> <sid> <ppid> <start> <json spec>: add a fake process (see fakeproc.py for the spec keys).
mkproc() { "$REAL_PY" "$FAKEPROC" mk "$@"; }
alive_fake() { [[ -d "$ROBOSIM_PROC_ROOT/$1" ]]; }
fake_clear() { rm -rf "$ROBOSIM_PROC_ROOT"/[0-9]*; }   # every fake process gone (as after a clean stop)

check() { # check <description> <expected> <actual>
  if [[ "$2" == "$3" ]]; then echo "PASS  $1"; else echo "FAIL  $1: expected '$2', got '$3'"; FAILS=$((FAILS + 1)); fi
}
check_grep() { # check_grep <description> <extended regex> <file>
  if grep -qE -- "$2" "$3" 2>/dev/null; then echo "PASS  $1"; else echo "FAIL  $1: /$2/ not in $3:"; sed 's/^/        /' "$3" 2>/dev/null | tail -30; FAILS=$((FAILS + 1)); fi
}
check_no_grep() { # check_no_grep <description> <extended regex> <file>
  if ! grep -qE -- "$2" "$3" 2>/dev/null; then echo "PASS  $1"; else echo "FAIL  $1: /$2/ found in $3:"; grep -nE -- "$2" "$3" | sed 's/^/        /'; FAILS=$((FAILS + 1)); fi
}
t_done() {
  [[ -n "$T" ]] && rm -rf "$T"
  if [[ $FAILS -eq 0 ]]; then echo "ALL PASS"; exit 0; fi
  echo "$FAILS FAILED"; exit 1
}
