#!/usr/bin/env bash
# map_overview.sh — RoboSim Eval D0d: print a coarse ASCII overview of the static map with the robot's current
# map-frame position (from TF map->base_link) and optional candidate points, to choose a reachable goal by eye.
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/map_overview.sh [<out_file>] [x,y ...]
# Legend: '#' occupied, '.' free, '?' unknown, 'R' robot, digits = candidate points in argument order. Read-only.
set -uo pipefail
OUT="${1:-/dev/stdout}"; shift || true
set +u
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh || exit 2
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh || exit 2
set -u
SHARE=$(ros2 pkg prefix carter_navigation)/share/carter_navigation
ROBOT=$(timeout 6 ros2 run tf2_ros tf2_echo map base_link 2>/dev/null | grep -m1 'Translation' | sed -E 's/.*\[([^]]*)\].*/\1/')
python3 - "$SHARE/maps/carter_warehouse_navigation.yaml" "${ROBOT:-}" "$@" > "$OUT" <<'PY'
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
[[ "$OUT" != /dev/stdout ]] && echo "written $OUT ($(wc -l < "$OUT") lines)"
