#!/usr/bin/env bash
# Show which clocksource the WSL kernel uses, the alternatives, and the kernel's time-sync settings (read-only, no sudo).
# Usage: bash -l clock_source.sh
set -uo pipefail
cs=/sys/devices/system/clocksource/clocksource0
echo "current_clocksource:   $(cat "$cs/current_clocksource")"
echo "available_clocksource: $(cat "$cs/available_clocksource")"
echo "kernel:                $(uname -r)"
echo "cmdline:               $(cat /proc/cmdline)"
echo "uptime_s:              $(cut -d' ' -f1 /proc/uptime)"
grep -m1 'model name' /proc/cpuinfo
grep -m1 'cpu MHz' /proc/cpuinfo
grep -o -w -E 'constant_tsc|nonstop_tsc|tsc_reliable|tsc_known_freq' /proc/cpuinfo | sort -u | tr '\n' ' '; echo
journalctl -k -b --no-pager 2>/dev/null | grep -i -E 'tsc|clocksource|hv_utils|timesync' | head -20 || echo "(journalctl -k not readable)"
