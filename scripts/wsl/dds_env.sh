# dds_env.sh — RoboSim Eval: Fast DDS profile for Windows<->WSL2 communication (plan doc B4).
# SOURCE after ros_env.sh in every Ubuntu terminal that must talk to Isaac Sim on Windows:
#   source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh
# Verifies the profile exists and is well-formed XML before exporting FASTRTPS_DEFAULT_PROFILES_FILE.

# Default: the profile of the checkout this file belongs to (a worktree uses its own configs/).
_robosim_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_robosim_dds="${ROBOSIM_DDS_PROFILE:-$_robosim_repo/configs/network/fastdds.xml}"
unset _robosim_repo

if [ ! -f "$_robosim_dds" ]; then
  echo "dds_env.sh: profile not found: $_robosim_dds" >&2; return 1 2>/dev/null || exit 1
fi
if ! python3 -c 'import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])' "$_robosim_dds" 2>/dev/null; then
  echo "dds_env.sh: profile is not well-formed XML: $_robosim_dds" >&2; return 1 2>/dev/null || exit 1
fi

export FASTRTPS_DEFAULT_PROFILES_FILE="$_robosim_dds"
echo "dds_env.sh: FASTRTPS_DEFAULT_PROFILES_FILE=$FASTRTPS_DEFAULT_PROFILES_FILE"
