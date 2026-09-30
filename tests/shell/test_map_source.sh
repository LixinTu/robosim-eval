#!/usr/bin/env bash
# Finding codex-b-7: the goal's free-space check (send_goal.sh) and the map preview (map_overview.sh) must use the map
# Nav2 actually loaded for this run, which start_nav2.sh records (path + sha256) in nav2-launch.meta, or fail clearly.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

mkmap() { # mkmap <yaml path> <fill 0=occupied 255=free> <width> <height>
  "$REAL_PY" - "$@" <<'PY'
import os, sys
from PIL import Image
path, fill, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
os.makedirs(os.path.dirname(path), exist_ok=True)
png = os.path.splitext(os.path.basename(path))[0] + ".png"
Image.new("L", (w, h), fill).save(os.path.join(os.path.dirname(path), png))
with open(path, "w") as f:
    f.write(f"image: {png}\nresolution: 0.1\norigin: [-2.0, -1.5, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.25\n")
PY
}
meta_of() { sed -n -E "s/^(.* )?$2=([^ ]*).*/\2/p" "$1/nav2-launch.meta" | tail -1; }

t_new start_nav2.sh send_goal.sh map_overview.sh
cd "$T" || exit 1
SHARE_MAP="$T/prefix/share/carter_navigation/maps/carter_warehouse_navigation.yaml"
mkmap "$SHARE_MAP" 0 50 40            # the package default: occupied everywhere
mkmap "$T/maps/custom.yaml" 255 40 30  # the map this run loads: free everywhere
echo "$T/prefix" > "$T/ros2/prefix"
: > "$T/ros2/nodes"
export FAKE_SPAWN=nav2

# start_nav2.sh records the map it hands to the launch: the package default, or the last map:= argument.
bash "$R/scripts/wsl/start_nav2.sh" "$T/run-default" > "$T/start1.txt" 2>&1
check "start_nav2 (default map): exit 0" 0 $?
check "start_nav2 (default map): map_yaml recorded" "$SHARE_MAP" "$(meta_of "$T/run-default" map_yaml)"
check "start_nav2 (default map): map_sha256 recorded" "$(sha256sum "$SHARE_MAP" | cut -d' ' -f1)" "$(meta_of "$T/run-default" map_sha256)"
fake_clear
bash "$R/scripts/wsl/start_nav2.sh" "$T/run" "map:=$T/maps/custom.yaml" > "$T/start2.txt" 2>&1
check "start_nav2 (map:=custom): exit 0" 0 $?
check "start_nav2 (map:=custom): map_yaml recorded" "$T/maps/custom.yaml" "$(meta_of "$T/run" map_yaml)"
check "start_nav2 (map:=custom): image sha256 recorded" "$(sha256sum "$T/maps/custom.png" | cut -d' ' -f1)" "$(meta_of "$T/run" map_image_sha256)"
fake_clear
bash "$R/scripts/wsl/start_nav2.sh" "$T/run-nomap" "map:=$T/maps/absent.yaml" > "$T/start3.txt" 2>&1
check "start_nav2 (map file missing): refused with exit 2" 2 $?

# send_goal.sh --check-only in an attempt dir below that run dir: checks against the run's map (free), not the
# package default (occupied).
mkdir -p "$T/run/attempt-01"
bash "$R/scripts/wsl/send_goal.sh" "$T/run/attempt-01" 0.0 0.0 0.0 --check-only > "$T/goal1.txt" 2>&1
check "send_goal: pose checked against the run's map -> free, exit 0" 0 $?
check_grep "send_goal: names the map it used" "custom.yaml" "$T/goal1.txt"
mkdir -p "$T/lonely"
bash "$R/scripts/wsl/send_goal.sh" "$T/lonely" 0.0 0.0 0.0 --check-only > "$T/goal2.txt" 2>&1
check "send_goal: no nav2-launch.meta and no --map -> exit 8" 8 $?
check_grep "send_goal: says how to name the map" "--nav2-run|--map" "$T/goal2.txt"
bash "$R/scripts/wsl/send_goal.sh" "$T/lonely" 0.0 0.0 0.0 --check-only --nav2-run "$T/run" > "$T/goal3.txt" 2>&1
check "send_goal: --nav2-run <run_dir> -> exit 0" 0 $?
bash "$R/scripts/wsl/send_goal.sh" "$T/lonely" 0.0 0.0 0.0 --check-only --map "$SHARE_MAP" > "$T/goal4.txt" 2>&1
check "send_goal: explicit --map (occupied) -> exit 3" 3 $?
bash "$R/scripts/wsl/send_goal.sh" "$T/run-default" 0.0 0.0 0.0 --check-only > "$T/goal5.txt" 2>&1
check "send_goal: run with the default map (occupied) -> exit 3" 3 $?
"$REAL_PY" -c 'from PIL import Image; Image.new("L", (40, 30), 0).save("'"$T"'/maps/custom.png")'
bash "$R/scripts/wsl/send_goal.sh" "$T/run/attempt-01" 0.0 0.0 0.0 --check-only > "$T/goal6.txt" 2>&1
check "send_goal: map image changed since Nav2 started -> exit 8" 8 $?
check_grep "send_goal: reports the changed map" "changed|differs" "$T/goal6.txt"
mkmap "$T/maps/custom.yaml" 255 40 30  # restore

# map_overview.sh: the run's map via --nav2-run, or via the out file's directory; no silent package default.
bash "$R/scripts/wsl/map_overview.sh" --nav2-run "$T/run" "$T/ov1.txt" > "$T/ov1.out" 2>&1
check "map_overview --nav2-run: exit 0" 0 $?
check_grep "map_overview --nav2-run: rendered the run's 40x30 map" "^map 40x30 px" "$T/ov1.txt"
bash "$R/scripts/wsl/map_overview.sh" "$T/run/map-overview.txt" > "$T/ov2.out" 2>&1
check "map_overview <run_dir>/file: exit 0" 0 $?
check_grep "map_overview <run_dir>/file: rendered the run's 40x30 map" "^map 40x30 px" "$T/run/map-overview.txt"
bash "$R/scripts/wsl/map_overview.sh" "$T/lonely/ov3.txt" > "$T/ov3.out" 2>&1
check "map_overview without a known map: exit 8" 8 $?
check "map_overview without a known map: nothing rendered" no "$([[ -s "$T/lonely/ov3.txt" ]] && echo yes || echo no)"
t_done
