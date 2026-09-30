#!/usr/bin/env bash
# Contract C6 / finding shell-10: the scripts derive the repository root from their own location, so a checkout in a
# git worktree runs its own code and configuration, never /mnt/d/RoboSim-Eval's.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

WSL_SCRIPTS=(start_nav2.sh stop_nav2.sh check_nav2_ready.sh record_d0.sh stop_record.sh send_goal.sh map_overview.sh
             ros_env.sh dds_env.sh install_ros2_jazzy.sh setup_workspace.sh check_ros_install.sh watch_clock.sh
             probe_env.sh probe_topics.sh diag_discovery.sh)
for s in "${WSL_SCRIPTS[@]}"; do
  hits=$(grep -nE '/mnt/d/RoboSim-Eval' "$SRC_REPO/scripts/wsl/$s" | grep -vE '^[0-9]+:[[:space:]]*#')
  check "$s: no hard-coded /mnt/d/RoboSim-Eval outside comments" "" "$hits"
done
for s in run_codex_review.ps1 run_codex_review_queue.ps1; do
  hits=$(grep -niE 'D:\\RoboSim-Eval' "$SRC_REPO/scripts/windows/$s" | grep -vE '^[0-9]+:[[:space:]]*#')
  check "$s: no hard-coded D:\\RoboSim-Eval outside comments" "" "$hits"
done

# dds_env.sh, sourced from another checkout, uses that checkout's Fast DDS profile.
t_new dds_env.sh
mkdir -p "$R/configs/network"
echo '<profiles/>' > "$R/configs/network/fastdds.xml"
got=$(env -u ROBOSIM_DDS_PROFILE bash -c 'source "$1" >/dev/null && echo "$FASTRTPS_DEFAULT_PROFILES_FILE"' _ "$R/scripts/wsl/dds_env.sh")
check "dds_env.sh: default profile comes from its own checkout" "$R/configs/network/fastdds.xml" "$got"
got=$(ROBOSIM_DDS_PROFILE="$R/configs/network/fastdds.xml" bash -c 'source "$1" >/dev/null && echo "$FASTRTPS_DEFAULT_PROFILES_FILE"' _ "$R/scripts/wsl/dds_env.sh")
check "dds_env.sh: ROBOSIM_DDS_PROFILE still overrides" "$R/configs/network/fastdds.xml" "$got"
t_done
