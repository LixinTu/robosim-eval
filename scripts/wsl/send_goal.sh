#!/usr/bin/env bash
# send_goal.sh — RoboSim Eval D0d: check a map-frame pose against the static map, then (unless --check-only) send it as
# ONE NavigateToPose goal through the CLI action client and keep the raw feedback/result (plan doc B6.4-5, A5).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/send_goal.sh <attempt_dir> <x> <y> <yaw_rad> [--check-only]
#        [--action /navigate_to_pose] [--settle 6] [--nav2-run <run_dir> | --map <map yaml>]
# The map is the one Nav2 loaded for this run: map_yaml in <run_dir>/nav2-launch.meta (written by start_nav2.sh;
# <run_dir> defaults to <attempt_dir> or, failing that, its parent), checked against the recorded sha256; --map names
# a map explicitly (e.g. --check-only before Nav2 runs). A pose is "free" when the map pixel value is above the free
# threshold. Also prints a small ASCII crop around the pose (#=occupied .=free ?=unknown).
# Output: <attempt_dir>/goal-<timestamp>.txt: first line "send_goal start ... x= y= yaw=" (the goal actually sent, read
# by analyze_attempt.py), then the wall-timestamped client output (feedback + result), last line with the real exit
# codes of the client and of the line stamper (transcriber) and the settle wait. Only the summary lines are printed to
# the terminal. After the result the script waits --settle seconds (default 6, wall, >= 0) so a running recorder also
# captures the robot coming to rest (stop-still window, plan doc A5).
# The client runs under `timeout -s INT -k 30 330`: SIGINT at 330 s makes it cancel the goal, and if it has not ended
# 30 s later (its cancel wait has no limit, e.g. with a hung action server) it is killed, so the script always ends.
# Exit: 0 goal SUCCEEDED; 2 bad arguments; 3 pose not free on the map; 4 action server not found;
#       5 goal finished but not SUCCEEDED (ABORTED/CANCELED/unknown); 6 goal rejected; 7 evidence incomplete: the
#       transcript's first line could not be written (nothing sent), the transcriber failed, the last line could not be
#       written or the settle wait failed (takes precedence over the client's status, which is printed);
#       8 the map Nav2 loaded is unknown or changed since the launch (nothing sent); other = action client exit code
#       (124 = stopped by the 330 s cap; 137 = still running 30 s after the cap and killed).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
ATT="${1:?attempt dir}"; X="${2:?x}"; Y="${3:?y}"; YAW="${4:?yaw rad}"; shift 4
CHECK_ONLY=no; ACTION=/navigate_to_pose; SETTLE=6; MAP_ARG=""; NAV2_RUN=""
while [[ $# -gt 0 ]]; do case "$1" in --check-only) CHECK_ONLY=yes;; --action) ACTION="$2"; shift;; --settle) SETTLE="$2"; shift;;
  --map) MAP_ARG="${2:?--map needs a map yaml}"; shift;; --nav2-run) NAV2_RUN="${2:?--nav2-run needs a run dir}"; shift;;
  *) echo "unknown arg $1"; exit 2;; esac; shift; done
if [[ -z "$MAP_ARG" && -z "$NAV2_RUN" ]]; then
  for d in "$ATT" "$(dirname "$ATT")"; do if [[ -f "$d/nav2-launch.meta" ]]; then NAV2_RUN="$d"; break; fi; done
fi
if ! python3 -c 'import sys, math; v = [float(a) for a in sys.argv[1:]]; sys.exit(0 if all(math.isfinite(x) for x in v) and v[3] >= 0 else 1)' "$X" "$Y" "$YAW" "$SETTLE"; then
  echo "ERROR: x, y, yaw (radians) must be finite numbers and --settle a finite number >= 0 (got x=$X y=$Y yaw=$YAW settle=$SETTLE)"; exit 2
fi
mkdir -p "$ATT"
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --full || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
# The map to check against (finding codex-b-7): --map as given, otherwise the map_yaml that start_nav2.sh recorded in
# nav2-launch.meta, verified by its sha256 (yaml and image) so a map changed since the launch is noticed.
meta_value() { sed -n -E "s/^(.* )?$1=([^ ]*).*/\2/p" "$META" 2>/dev/null | tail -1; }
MAP_SHA=""; IMG_SHA=""
if [[ -n "$MAP_ARG" ]]; then
  MAPYAML="$MAP_ARG"; MAP_FROM="--map"
else
  META="$NAV2_RUN/nav2-launch.meta"
  if [[ -z "$NAV2_RUN" || ! -f "$META" ]]; then
    echo "ERROR: cannot tell which map Nav2 loaded: ${NAV2_RUN:-$ATT (and its parent)} has no nav2-launch.meta;"
    echo "       pass --nav2-run <run_dir given to start_nav2.sh> or --map <map yaml>"; exit 8
  fi
  MAPYAML=$(meta_value map_yaml); MAP_SHA=$(meta_value map_sha256); IMG_SHA=$(meta_value map_image_sha256)
  if [[ -z "$MAPYAML" || -z "$MAP_SHA" || -z "$IMG_SHA" ]]; then
    echo "ERROR: $META records no map identity (written by an older start_nav2.sh); pass --map <map yaml>"; exit 8
  fi
  MAP_FROM="$META"
fi
echo "map: $MAPYAML (from $MAP_FROM)"
python3 - "$MAPYAML" "$MAP_SHA" "$IMG_SHA" <<'PY' || exit 8
import hashlib, os, sys
import yaml
path, want_yaml, want_image = sys.argv[1:4]
def sha(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()
try:
    with open(path) as f:
        image = os.path.join(os.path.dirname(path), yaml.safe_load(f)['image'])
    got_yaml, got_image = sha(path), sha(image)
except (OSError, yaml.YAMLError, KeyError, TypeError) as exc:
    print(f"ERROR: map {path} cannot be read ({type(exc).__name__}: {exc})")
    sys.exit(1)
if want_yaml and (got_yaml, got_image) != (want_yaml, want_image):
    print(f"ERROR: map {path} changed since Nav2 started: sha256 now yaml {got_yaml} image {got_image}, "
          f"recorded yaml {want_yaml} image {want_image}")
    sys.exit(1)
PY

python3 - "$MAPYAML" "$X" "$Y" <<'PY' || { echo "pose check FAILED (see above)"; exit 3; }
import sys, math, yaml, os
from PIL import Image
mapyaml, x, y = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
m = yaml.safe_load(open(mapyaml)); res = m['resolution']; ox, oy, _ = m['origin']
img = Image.open(os.path.join(os.path.dirname(mapyaml), m['image'])).convert('L'); W, H = img.size
negate = int(m.get('negate', 0)); free_t = m['free_thresh']; occ_t = m['occupied_thresh']
def occ(px, py):  # occupancy probability of pixel (col, row from top)
    v = img.getpixel((px, py)) / 255.0
    return v if negate else 1.0 - v
col = int((x - ox) / res); row = H - 1 - int((y - oy) / res)
if not (0 <= col < W and 0 <= row < H):
    print(f"pose ({x}, {y}) is OUTSIDE the map ({W}x{H} px, res {res}, origin ({ox}, {oy}))"); sys.exit(1)
p = occ(col, row)
state = 'FREE' if p < free_t else ('OCCUPIED' if p > occ_t else 'UNKNOWN')
# clearance: nearest occupied pixel within 1.0 m
r = int(1.0 / res); nearest = None
for dy in range(-r, r + 1):
    for dx in range(-r, r + 1):
        cx, cy = col + dx, row + dy
        if 0 <= cx < W and 0 <= cy < H and occ(cx, cy) > occ_t:
            d = math.hypot(dx, dy) * res
            if nearest is None or d < nearest: nearest = d
print(f"map {W}x{H} px, res {res} m/px, origin ({ox}, {oy}); pose ({x}, {y}) -> pixel col {col} row {row}: occupancy {p:.2f} => {state}; nearest obstacle within 1 m: {('%.2f m' % nearest) if nearest is not None else 'none'}")
crop = 12
for dy in range(-crop, crop + 1):
    line = ''
    for dx in range(-crop, crop + 1):
        cx, cy = col + dx, row + dy
        if dx == 0 and dy == 0: line += 'X'; continue
        if not (0 <= cx < W and 0 <= cy < H): line += ' '; continue
        q = occ(cx, cy); line += '#' if q > occ_t else ('.' if q < free_t else '?')
    print(line)
print(f"(crop is {2*crop+1} px = {(2*crop+1)*res:.2f} m wide; X marks the pose; up = +y)")
sys.exit(0 if state == 'FREE' else 1)
PY
if [[ $CHECK_ONLY == yes ]]; then echo "check-only: not sending"; exit 0; fi

if ! timeout 15 ros2 action list 2>/dev/null | grep -qx "$ACTION"; then echo "ERROR: action $ACTION not found in ros2 action list"; exit 4; fi
QZ=$(python3 -c 'import sys, math; print(math.sin(float(sys.argv[1]) / 2))' "$YAW")
QW=$(python3 -c 'import sys, math; print(math.cos(float(sys.argv[1]) / 2))' "$YAW")
GOAL="{pose: {header: {frame_id: map}, pose: {position: {x: $X, y: $Y, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: $QZ, w: $QW}}}}"
OUT="$ATT/goal-$(date +%H%M%S).txt"
if ! echo "send_goal start $(date -Is) action=$ACTION frame=map x=$X y=$Y yaw=$YAW qz=$QZ qw=$QW map=$MAPYAML sim_time_before=$(timeout 3 ros2 topic echo --once --field clock.sec /clock 2>/dev/null | tr -d '\n-')" > "$OUT"; then
  echo "ERROR: cannot write the transcript $OUT; goal not sent"; exit 7
fi
timeout -s INT -k 30 330 ros2 action send_goal "$ACTION" nav2_msgs/action/NavigateToPose "$GOAL" --feedback 2>&1 \
  | python3 -u -c 'import sys, datetime
for line in sys.stdin: print(datetime.datetime.now().isoformat(timespec="milliseconds"), line.rstrip())' >> "$OUT"
PS=("${PIPESTATUS[@]}"); CLIENT_RC=${PS[0]}; STAMP_RC=${PS[1]}   # both statuses, saved at once (finding codex-b-3)
SETTLE_RC=0
if [[ "$SETTLE" != 0 ]]; then sleep "$SETTLE"; SETTLE_RC=$?; fi
INCOMPLETE=()
if ! echo "send_goal end $(date -Is) action_client_exit=$CLIENT_RC transcriber_exit=$STAMP_RC settle_s=$SETTLE settle_exit=$SETTLE_RC sim_time_after=$(timeout 3 ros2 topic echo --once --field clock.sec /clock 2>/dev/null | tr -d '\n-')" >> "$OUT"; then
  INCOMPLETE+=("the transcript's end line could not be written")
fi
[[ $STAMP_RC -eq 0 ]] || INCOMPLETE+=("the transcriber exited $STAMP_RC, so client output may be missing from the transcript")
[[ $SETTLE_RC -eq 0 ]] || INCOMPLETE+=("the --settle wait failed (sleep exit $SETTLE_RC): no stop-still window recorded")
grep -E 'send_goal (start|end)|Goal accepted|Goal was rejected|Goal finished with status|error_code:|error_msg:' "$OUT"
echo "transcript: $OUT ($(wc -l < "$OUT") lines)"
case $CLIENT_RC in
  0) ;;
  124) echo "action client stopped by the 330 s cap (SIGINT, exit 124)" ;;
  137) echo "action client still running 30 s after the 330 s cap's SIGINT: killed (SIGKILL, exit 137)" ;;
  *) echo "action client exited $CLIENT_RC" ;;
esac
if [[ ${#INCOMPLETE[@]} -gt 0 ]]; then printf 'ERROR: evidence incomplete: %s\n' "${INCOMPLETE[@]}"; exit 7; fi
if [[ $CLIENT_RC -ne 0 ]]; then exit "$CLIENT_RC"; fi
if grep -q 'Goal finished with status: SUCCEEDED' "$OUT"; then exit 0; fi
if grep -q 'Goal was rejected' "$OUT"; then exit 6; fi
exit 5
