#!/usr/bin/env bash
# Re-evaluate every recorded real run in memory with the analyzer of the checkout given as $1 (default: this checkout)
# and compare with the recorded verdict. Reads artifacts/ only; writes nothing.
set +u
source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full >/dev/null || exit 2
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKOUT="${1:-$(cd "$HERE/../.." && pwd)}"
PYTHONDONTWRITEBYTECODE=1 python3 "$HERE/regress_analyzer.py" "$CHECKOUT" 2>&1 | grep -v '^\[INFO\]'
