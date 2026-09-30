#!/usr/bin/env bash
# send_goal.sh — RoboSim Eval D0d: check a map-frame pose against the static map, then (unless --check-only) send it as
# ONE NavigateToPose goal through the CLI action client and keep the raw feedback/result (plan doc B6.4-5, A5).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/send_goal.sh <attempt_dir> <x> <y> <yaw_rad> [--check-only]
#        [--action /navigate_to_pose] [--settle 6]
# The map is read from the pinned carter_navigation share (yaml origin/resolution + png); a pose is "free" when the
# map pixel value is above the free threshold. Also prints a small ASCII crop around the pose (#=occupied .=free ?=unknown).
# Output: <attempt_dir>/goal-<timestamp>.txt: first line "send_goal start ... x= y= yaw=" (the goal actually sent, read
# by analyze_attempt.py), then the wall-timestamped client output (feedback + result), last line with the client's real
# exit code. Only the summary lines are printed to the terminal. After the result the script waits --settle seconds
# (default 6, wall) so a running recorder also captures the robot coming to rest (stop-still window, plan doc A5).
# Exit: 0 goal SUCCEEDED; 2 bad arguments; 3 pose not free on the map; 4 action server not found;
#       5 goal finished but not SUCCEEDED (ABORTED/CANCELED/unknown); 6 goal rejected; other = action client exit code
#       (e.g. 124 when the 330 s client timeout fired).
set -uo pipefail
ATT="${1:?attempt dir}"; X="${2:?x}"; Y="${3:?y}"; YAW="${4:?yaw rad}"; shift 4
CHECK_ONLY=no; ACTION=/navigate_to_pose; SETTLE=6
while [[ $# -gt 0 ]]; do case "$1" in --check-only) CHECK_ONLY=yes;; --action) ACTION="$2"; shift;; --settle) SETTLE="$2"; shift;; *) echo "unknown arg $1"; exit 2;; esac; shift; done
if ! python3 -c 'import sys, math; v = [float(a) for a in sys.argv[1:]]; sys.exit(0 if all(math.isfinite(x) for x in v) else 1)' "$X" "$Y" "$YAW" "$SETTLE"; then
  echo "ERROR: x, y, yaw (radians) and --settle must be finite numbers (got x=$X y=$Y yaw=$YAW settle=$SETTLE)"; exit 2
fi
mkdir -p "$ATT"
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
SHARE=$(ros2 pkg prefix carter_navigation)/share/carter_navigation
MAPYAML="$SHARE/maps/carter_warehouse_navigation.yaml"

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
echo "send_goal start $(date -Is) action=$ACTION frame=map x=$X y=$Y yaw=$YAW qz=$QZ qw=$QW sim_time_before=$(timeout 3 ros2 topic echo --once --field clock.sec /clock 2>/dev/null | tr -d '\n-')" > "$OUT"
timeout -s INT 330 ros2 action send_goal "$ACTION" nav2_msgs/action/NavigateToPose "$GOAL" --feedback 2>&1 \
  | python3 -u -c 'import sys, datetime
for line in sys.stdin: print(datetime.datetime.now().isoformat(timespec="milliseconds"), line.rstrip())' >> "$OUT"
CLIENT_RC=${PIPESTATUS[0]}
if [[ "$SETTLE" != 0 ]]; then sleep "$SETTLE"; fi
echo "send_goal end $(date -Is) action_client_exit=$CLIENT_RC settle_s=$SETTLE sim_time_after=$(timeout 3 ros2 topic echo --once --field clock.sec /clock 2>/dev/null | tr -d '\n-')" >> "$OUT"
grep -E 'send_goal (start|end)|Goal accepted|Goal was rejected|Goal finished with status|error_code:|error_msg:' "$OUT"
echo "transcript: $OUT ($(wc -l < "$OUT") lines)"
if [[ $CLIENT_RC -ne 0 ]]; then echo "action client exited $CLIENT_RC"; exit "$CLIENT_RC"; fi
if grep -q 'Goal finished with status: SUCCEEDED' "$OUT"; then exit 0; fi
if grep -q 'Goal was rejected' "$OUT"; then exit 6; fi
exit 5
