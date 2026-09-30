#!/usr/bin/env bash
# send_goal.sh around the CLI action client:
#   shell-6    the 330 s client cap is a hard bound (timeout -k) and a kill after the cap is reported;
#   codex-b-3  the transcriber's exit status and the transcript's first/last line writes are checked, not only the
#              client's status (an incomplete transcript is exit 7 even when it already says SUCCEEDED);
#   codex-b-9  --settle must be >= 0 (checked before anything is sent) and a failed settle wait is an error.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

t_new send_goal.sh
cd "$T" || exit 1
"$REAL_PY" - "$T/maps/free.yaml" <<'PY'
import os, sys
from PIL import Image
path = sys.argv[1]; os.makedirs(os.path.dirname(path), exist_ok=True)
Image.new("L", (40, 30), 255).save(os.path.join(os.path.dirname(path), "free.png"))
open(path, "w").write("image: free.png\nresolution: 0.1\norigin: [-2.0, -1.5, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n")
PY
echo "/navigate_to_pose" > "$T/ros2/actions"
echo "100" > "$T/ros2/echo"
printf '%s\n' "Waiting for an action server to become available..." "Goal accepted with ID: 1234" \
  "Result:" "    error_code: 0" "Goal finished with status: SUCCEEDED" > "$T/ros2/send_goal"
goal() { # goal <attempt_dir> [extra args...]: send (0,0,0) against the free map; sets RC
  local att="$1"; shift
  bash "$R/scripts/wsl/send_goal.sh" "$att" 0.0 0.0 0.0 --map "$T/maps/free.yaml" "$@" > "$T/out.txt" 2>&1; RC=$?
}
reset_calls() { : > "$T/calls.log"; }

goal "$T/a1"
check "SUCCEEDED -> exit 0" 0 "$RC"
check_grep "client bounded: timeout -s INT -k <s> 330 around the CLI client (shell-6)" '^timeout -s INT -k [0-9]+ 330 ros2 action send_goal' "$T/calls.log"
check_grep "end line records the client and the transcriber exit" 'send_goal end .*action_client_exit=0 transcriber_exit=0' "$T"/a1/goal-*.txt
check_grep "settle wait of 6 s by default" '^sleep 6$' "$T/calls.log"

echo 137 > "$T/ros2/send_goal.rc"
goal "$T/a2"
check "client killed after the cap -> its exit code 137" 137 "$RC"
check_grep "a kill after the cap is named as such" 'killed' "$T/out.txt"
rm -f "$T/ros2/send_goal.rc"

FAKE_STAMP_FAIL=1 goal "$T/a3"
check "transcriber fails at once -> exit 7 (transcript incomplete)" 7 "$RC"
check_grep "transcriber failure reported" 'transcriber' "$T/out.txt"
cat > "$T/bin/python3" <<'EOF'
#!/bin/bash
# the stamper writes every line, then fails (e.g. a write error at close): the transcript already says SUCCEEDED
if [[ "$*" == *datetime.datetime.now* ]]; then "$REAL_PY" "$@"; exit 7; fi
exec "$REAL_PY" "$@"
EOF
goal "$T/a4"
check "transcriber fails after writing SUCCEEDED -> exit 7, not 0" 7 "$RC"
check_grep "the transcriber's status is in the end line" 'send_goal end .*transcriber_exit=7' "$T"/a4/goal-*.txt
printf '#!/bin/bash\nexec "$REAL_PY" "$@"\n' > "$T/bin/python3"

mkdir -p "$T/a5"; chmod a-w "$T/a5"; reset_calls
goal "$T/a5"
check "transcript cannot be created -> exit 7" 7 "$RC"
check_no_grep "nothing sent when the transcript cannot be written" 'action send_goal' "$T/calls.log"
chmod u+w "$T/a5"

cat > "$T/bin/sleep" <<'EOF'
#!/bin/bash
echo "sleep $*" >> "$FAKE_T/calls.log"
chmod a-w "$FAKE_T"/a6/goal-*.txt   # the transcript becomes read-only during the settle wait
EOF
goal "$T/a6"
check "end line cannot be appended -> exit 7" 7 "$RC"
check_grep "the missing end line is reported" 'end line' "$T/out.txt"
chmod u+w "$T"/a6/goal-*.txt
printf '#!/bin/bash\necho "sleep $*" >> "$FAKE_T/calls.log"\nexit 1\n' > "$T/bin/sleep"
goal "$T/a7"
check "settle wait fails -> exit 7" 7 "$RC"
check_grep "the failed settle wait is in the end line" 'send_goal end .*settle_exit=1' "$T"/a7/goal-*.txt
printf '#!/bin/bash\necho "sleep $*" >> "$FAKE_T/calls.log"\n' > "$T/bin/sleep"

reset_calls
goal "$T/a8" --settle -1
check "--settle -1 -> exit 2" 2 "$RC"
check_no_grep "--settle -1: nothing sent" 'action send_goal' "$T/calls.log"
goal "$T/a9" --settle 0
check "--settle 0 -> exit 0 without a wait" 0 "$RC"
t_done
