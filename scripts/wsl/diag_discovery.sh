#!/usr/bin/env bash
# diag_discovery.sh — RoboSim Eval D0c: why does WSL not see Isaac Sim's DDS participants? (plan doc C: 两端发现不了节点)
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/diag_discovery.sh [<out_dir>]
# Read-only diagnostics, nothing is published to ROS topics:
#   1. WSL network facts (own IP, gateway = Windows host on the vEthernet (WSL) switch, ufw state)
#   2. Passive multicast capture on the DDS SPDP group 239.255.0.1:7400 for 12 s: which source IPs announce?
#      (172.28.208.1 = Isaac on the Windows host; our own IP = WSL's own ros2 daemon)
#   3. Discovery with a longer wait: daemon restart, 10 s, then node/topic list; then a no-daemon list with spin time
#   4. WSL's own DDS sockets (ss)
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # this checkout (a worktree runs its own code)
OUT="${1:-$REPO/artifacts/d0c/diag-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
set +u
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/ros_env.sh" --base-only || exit 2
# shellcheck disable=SC1091
source "$REPO/scripts/wsl/dds_env.sh" || exit 2
set -u
run() { local title="$1"; shift; echo; echo "===== $title ====="; echo "CMD: $*"; "$@"; echo "EXIT: $?"; }

{
echo "=== diag_discovery.sh $(date -Is) RMW=$RMW_IMPLEMENTATION DOMAIN=$ROS_DOMAIN_ID profile=$FASTRTPS_DEFAULT_PROFILES_FILE ==="
MYIP=$(ip -4 addr show eth0 | awk '/inet /{print $2}' | cut -d/ -f1)
GW=$(ip route | awk '/default/{print $3}')
echo "WSL eth0 ip=$MYIP gateway(windows host)=$GW"
run "ufw config" bash -c 'grep -H ENABLED /etc/ufw/ufw.conf 2>/dev/null || echo "ufw not present"'
run "ping windows host (3 pkts)" timeout 6 ping -c 3 -W 1 "$GW"

echo; echo "===== passive multicast capture 239.255.0.1:7400 for 12 s ====="
python3 - "$MYIP" <<'PY'
import socket, struct, sys, time, collections
myip = sys.argv[1]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try: s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
except OSError: pass
s.bind(("0.0.0.0", 7400))
mreq = struct.pack("4s4s", socket.inet_aton("239.255.0.1"), socket.inet_aton(myip))
s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
s.settimeout(0.5)
counts = collections.Counter(); rtps = collections.Counter()
t_end = time.time() + 12
while time.time() < t_end:
    try:
        data, (ip, port) = s.recvfrom(65535)
    except socket.timeout:
        continue
    counts[ip] += 1
    if data[:4] == b"RTPS": rtps[ip] += 1
print("packets by source ip:", dict(counts) or "NONE")
print("RTPS-magic packets by source ip:", dict(rtps) or "NONE")
print("EXIT: 0")
PY

echo; echo "===== discovery with 10 s wait after daemon restart ====="
ros2 daemon stop >/dev/null 2>&1; sleep 1; ros2 daemon start >/dev/null 2>&1; sleep 10
run "node list (daemon)" timeout 15 ros2 node list
run "topic list (daemon)" timeout 15 ros2 topic list
run "topic list (no daemon, spin 8 s)" timeout 20 ros2 topic list --no-daemon --spin-time 8
run "wsl own dds sockets" bash -c 'ss -ulnp 2>/dev/null | grep -E ":74[0-9]{2} |:7[0-9]{3} " || echo "no 7xxx udp sockets listed"'
} 2>&1 | tee "$OUT/diag.txt"
TEE_RC=${PIPESTATUS[1]}
echo "written: $OUT/diag.txt (tee exit $TEE_RC)"
exit $TEE_RC
