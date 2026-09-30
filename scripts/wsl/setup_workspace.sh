#!/usr/bin/env bash
# setup_workspace.sh — RoboSim Eval D0b: clone the pinned IsaacSim-ros_workspaces tag and build carter_navigation.
# Needs ROS 2 Jazzy installed (install_ros2_jazzy.sh) and no sudo (rosdep is run with --simulate first; if it would
# need to install something, the script stops and prints the list instead of calling sudo).
#   bash /mnt/d/RoboSim-Eval/scripts/wsl/setup_workspace.sh
# Idempotent: an existing checkout is verified (tag commit, clean tree, submodules) and reused, never force-reset.
# Log: /mnt/d/RoboSim-Eval/artifacts/d0b/setup-workspace.log ; exit code: .../setup-workspace.exit
set -euo pipefail

EXPECTED_COMMIT=a9e8471ee901bc2332c1e4aca94ac580713ca3ab
TAG=IsaacSim-6.1.0
WS_ROOT="${ROBOSIM_VENDOR_ROOT:-$HOME/robotics/vendor/isaac-ros-6.1}"
LOG_DIR=/mnt/d/RoboSim-Eval/artifacts/d0b
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/setup-workspace.log"
exec > >(tee -a "$LOG") 2>&1
trap 'rc=$?; echo; echo "=== setup_workspace.sh end $(date -Is) exit=$rc ==="; echo "$rc" > "$LOG_DIR/setup-workspace.exit"' EXIT

echo "=== setup_workspace.sh start $(date -Is) user=$(id -un) ws=$WS_ROOT ==="
step() { echo; echo "--- [$(date +%T)] $* ---"; }

step "0. base ROS environment"
# shellcheck disable=SC1091
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --base-only

step "1. checkout $TAG"
if [[ -d "$WS_ROOT/.git" ]]; then
  echo "existing checkout found, verifying (no force checkout, no clean)"
else
  mkdir -p "$(dirname "$WS_ROOT")"
  git clone --branch "$TAG" --depth 1 --recurse-submodules https://github.com/isaac-sim/IsaacSim-ros_workspaces.git "$WS_ROOT"
fi
cd "$WS_ROOT"
HEAD_COMMIT=$(git rev-parse HEAD)
echo "HEAD=$HEAD_COMMIT  expected=$EXPECTED_COMMIT"
echo "describe: $(git describe --tags --always)"
echo "status:"; git status --short
echo "submodules:"; git submodule status || echo "(no submodules)"
if [[ "$HEAD_COMMIT" != "$EXPECTED_COMMIT" ]]; then echo "ERROR: HEAD does not match the pinned commit; stopping for review"; exit 4; fi
if [[ -n "$(git status --porcelain)" ]]; then echo "ERROR: checkout is dirty; stopping for review (not cleaning user changes)"; exit 5; fi

step "2. package closure"
cd "$WS_ROOT/jazzy_ws"
colcon list --packages-up-to carter_navigation
PKG_PATHS=$(colcon list --packages-up-to carter_navigation --paths-only)
echo "paths: $PKG_PATHS"

step "3. rosdep (simulate; stop if anything would be installed)"
# shellcheck disable=SC2086
if ! rosdep install --from-paths $PKG_PATHS --ignore-src -r --simulate; then echo "rosdep --simulate reported unresolved keys (see above); continuing so the build result is recorded"; fi
# shellcheck disable=SC2086
MISSING=$(rosdep install --from-paths $PKG_PATHS --ignore-src -r --simulate 2>/dev/null | grep -E '^\s*(sudo|apt)' || true)
if [[ -n "$MISSING" ]]; then
  echo "ERROR: rosdep would install packages (needs sudo). Add them to install_ros2_jazzy.sh and re-run it:"; echo "$MISSING"; exit 6
fi
echo "rosdep: nothing to install"

step "4. colcon build --packages-up-to carter_navigation"
colcon build --packages-up-to carter_navigation --event-handlers console_direct+ --cmake-args -DCMAKE_BUILD_TYPE=Release
echo "build finished; packages in install/: $(ls install | tr '\n' ' ')"

step "5. overlay checks"
# shellcheck disable=SC1091
source install/setup.bash
echo "carter_navigation prefix: $(ros2 pkg prefix carter_navigation)"
ros2 launch carter_navigation carter_navigation.launch.xml --show-args
SHARE=$(ros2 pkg prefix carter_navigation)/share/carter_navigation
echo "map yaml sha256:   $(sha256sum "$SHARE/maps/carter_warehouse_navigation.yaml")"
echo "map image sha256:  $(sha256sum "$SHARE/maps/carter_warehouse_navigation.png")"
echo "params sha256:     $(sha256sum "$SHARE/params/carter_navigation_params.yaml")"
echo "launch sha256:     $(sha256sum "$SHARE/launch/carter_navigation.launch.xml")"
echo "ALL STEPS COMPLETED"
