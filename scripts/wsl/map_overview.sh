#!/usr/bin/env bash
# map_overview.sh — RoboSim Eval D0d: print a coarse ASCII overview of the static map with the robot's current
# map-frame position (from TF map->base_link) and optional candidate points, to choose a reachable goal by eye.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/map_overview.sh [--nav2-run <run_dir> | --map <yaml>]
#        [<out_file>] [x,y ...]
# The map is the one Nav2 loaded: map_yaml in <run_dir>/nav2-launch.meta (start_nav2.sh), checked against the recorded
# sha256; <run_dir> defaults to the out file's directory. --map names a map explicitly. Without either: exit 8.
# Legend: '#' occupied, '.' free, '?' unknown, 'R' robot, digits = candidate points in argument order. Read-only.
# Exit: 8 the map is unknown or changed since the launch (nothing rendered); otherwise the rendering step's status
#       (0 = overview written).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
MAP_ARG=""; NAV2_RUN=""
while [[ $# -gt 0 ]]; do case "$1" in
  --map) MAP_ARG="${2:?--map needs a map yaml}"; shift 2;; --nav2-run) NAV2_RUN="${2:?--nav2-run needs a run dir}"; shift 2;;
  *) break;; esac; done
OUT="${1:-/dev/stdout}"; shift || true
if [[ -z "$MAP_ARG" && -z "$NAV2_RUN" && "$OUT" != /dev/stdout && -f "$(dirname "$OUT")/nav2-launch.meta" ]]; then
  NAV2_RUN="$(dirname "$OUT")"
fi
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
    echo "ERROR: cannot tell which map Nav2 loaded: ${NAV2_RUN:-the directory of the out file} has no nav2-launch.meta;"
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
ROBOT=$(timeout 6 ros2 run tf2_ros tf2_echo map base_link 2>/dev/null | grep -m1 'Translation' | sed -E 's/.*\[([^]]*)\].*/\1/')
python3 - "$MAPYAML" "${ROBOT:-}" "$@" > "$OUT" <<'PY'
import sys, os, yaml
from PIL import Image
mapyaml, robot = sys.argv[1], sys.argv[2]
cands = [tuple(float(v) for v in a.split(',')) for a in sys.argv[3:]]
m = yaml.safe_load(open(mapyaml)); res = m['resolution']; ox, oy, _ = m['origin']
img = Image.open(os.path.join(os.path.dirname(mapyaml), m['image'])).convert('L'); W, H = img.size
negate = int(m.get('negate', 0)); free_t = m['free_thresh']; occ_t = m['occupied_thresh']
cell = 0.5  # metres per character
cw = max(1, int(cell / res)); ch = cw * 2  # rows are twice as tall as wide in a terminal
def occ(px, py):
    v = img.getpixel((px, py)) / 255.0
    return v if negate else 1.0 - v
def cell_char(c0, r0):
    occs = []
    for yy in range(r0, min(H, r0 + ch)):
        for xx in range(c0, min(W, c0 + cw)):
            occs.append(occ(xx, yy))
    if not occs: return ' '
    if max(occs) > occ_t: return '#'
    if min(occs) < free_t and sum(1 for o in occs if o < free_t) > len(occs) * 0.5: return '.'
    return '?'
def to_cell(x, y):
    col = int((x - ox) / res); row = H - 1 - int((y - oy) / res)
    return col // cw, row // ch
marks = {}
if robot:
    rx, ry = [float(v) for v in robot.split(',')[:2]]
    marks[to_cell(rx, ry)] = 'R'
    print(f"robot (map) = ({rx:.2f}, {ry:.2f})")
for i, (x, y) in enumerate(cands, 1):
    marks[to_cell(x, y)] = str(i % 10); print(f"candidate {i} = ({x}, {y})")
print(f"map {W}x{H} px @ {res} m/px, origin ({ox}, {oy}); one char = {cell} m wide x {cell*2} m tall; up = +y, right = +x")
rows = (H + ch - 1) // ch; cols = (W + cw - 1) // cw
for r in range(rows):
    y_top = oy + (H - r * ch) * res
    line = ''.join(marks.get((c, r), cell_char(c * cw, r * ch)) for c in range(cols))
    print(f"{y_top:7.2f} |{line}|")
xs = ''.join(('|' if (c % 10 == 0) else ' ') for c in range(cols))
print(f"{'':7} +{xs}+")
print(f"{'':7}  x labels every 10 chars (5 m) starting at x={ox:.2f}: " + ' '.join(f"{ox + c*cell:.1f}" for c in range(0, cols, 10)))
PY
PYRC=$?
if [[ "$OUT" != /dev/stdout ]]; then echo "written $OUT ($(wc -l < "$OUT") lines)"; fi
exit $PYRC
