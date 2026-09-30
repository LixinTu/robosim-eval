#!/usr/bin/env bash
# Finding critic-5: re-running the one-time install/setup scripts must not append to or overwrite the tracked D0b
# evidence (artifacts/d0b/*.log, *.exit); by default they write to a new timestamped directory, and an explicit
# path is honoured. The scripts are stopped at their first privileged or networked step by failing stubs.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

stub_fail() { local c; for c in "$@"; do printf '#!/bin/bash\necho "%s stub: refused $*" >&2\nexit 1\n' "$c" > "$T/bin/$c"; chmod +x "$T/bin/$c"; done; }
seed_d0b() {
  mkdir -p "$R/artifacts/d0b"
  local n; for n in "$@"; do echo "ORIGINAL LOG" > "$R/artifacts/d0b/$n.log"; echo 0 > "$R/artifacts/d0b/$n.exit"; done
  (cd "$R/artifacts/d0b" && md5sum ./* > "$T/d0b.md5")
}
d0b_unchanged() { (cd "$R/artifacts/d0b" && md5sum ./*) | diff -q - "$T/d0b.md5" >/dev/null && echo yes || echo no; }

# install_ros2_jazzy.sh: stops at `sudo -v` (stub fails).
t_new install_ros2_jazzy.sh
stub_fail sudo apt-get curl
seed_d0b install-jazzy
bash "$R/scripts/wsl/install_ros2_jazzy.sh" > "$T/out.txt" 2>&1; rc=$?
check "install: stub sudo stops the script (non-zero exit)" yes "$([[ $rc -ne 0 ]] && echo yes || echo no)"
check "install: tracked artifacts/d0b evidence unchanged" yes "$(d0b_unchanged)"
new=$(ls -d "$R"/artifacts/setup-*/ 2>/dev/null | head -1)
check "install: log written to a new artifacts/setup-<time>/ directory" yes "$([[ -n "$new" && -f "$new/install-jazzy.log" ]] && echo yes || echo no)"
check "install: exit code file next to that log" "$rc" "$(cat "$new/install-jazzy.exit" 2>/dev/null)"
check_grep "install: the new log has the start line" 'install_ros2_jazzy.sh start' "$new/install-jazzy.log"

ROBOSIM_INSTALL_LOG="$T/explicit/inst.log" bash "$R/scripts/wsl/install_ros2_jazzy.sh" > "$T/out2.txt" 2>&1; rc=$?
check "install: explicit ROBOSIM_INSTALL_LOG is honoured" yes "$([[ -f "$T/explicit/inst.log" ]] && echo yes || echo no)"
check "install: explicit path gets its .exit" "$rc" "$(cat "$T/explicit/inst.exit" 2>/dev/null)"
check "install: tracked evidence still unchanged" yes "$(d0b_unchanged)"

# setup_workspace.sh: stops at step 0 (the stub ros_env.sh fails); git/colcon/rosdep stubs fail too, and the vendor
# root points into the temp dir, so the real workspace is never touched.
t_new setup_workspace.sh
printf '%s\n' 'echo "stub ros_env.sh: failing on purpose" >&2' 'return 1' > "$R/scripts/wsl/ros_env.sh"
stub_fail git colcon rosdep
seed_d0b setup-workspace
ROBOSIM_VENDOR_ROOT="$T/vendor" bash "$R/scripts/wsl/setup_workspace.sh" > "$T/out.txt" 2>&1; rc=$?
check "setup: failing ros_env stops the script (non-zero exit)" yes "$([[ $rc -ne 0 ]] && echo yes || echo no)"
check "setup: tracked artifacts/d0b evidence unchanged" yes "$(d0b_unchanged)"
new=$(ls -d "$R"/artifacts/setup-*/ 2>/dev/null | head -1)
check "setup: log written to a new artifacts/setup-<time>/ directory" yes "$([[ -n "$new" && -f "$new/setup-workspace.log" ]] && echo yes || echo no)"
check "setup: exit code file next to that log" "$rc" "$(cat "$new/setup-workspace.exit" 2>/dev/null)"
ROBOSIM_VENDOR_ROOT="$T/vendor" ROBOSIM_SETUP_LOG="$T/explicit/ws.log" bash "$R/scripts/wsl/setup_workspace.sh" > "$T/out2.txt" 2>&1; rc=$?
check "setup: explicit ROBOSIM_SETUP_LOG is honoured" "$rc" "$(cat "$T/explicit/ws.exit" 2>/dev/null)"
check "setup: tracked evidence still unchanged" yes "$(d0b_unchanged)"
t_done
