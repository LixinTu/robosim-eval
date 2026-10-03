#!/usr/bin/env bash
# Read-only: is hv_utils' timesync_implicit a runtime-writable parameter, and is any NTP/PTP client disciplining the clock?
p=/sys/module/hv_utils/parameters/timesync_implicit
ls -l "$p" 2>&1
echo "value: $(cat "$p" 2>&1)"
ls /sys/module/hv_utils/parameters/ 2>&1
echo "--- time daemons"
pgrep -a -f 'chronyd|ntpd|systemd-timesyncd|ptp4l|phc2sys' || echo "none running"
timedatectl show 2>/dev/null | grep -E 'NTP|Synchronized' || echo "(timedatectl unavailable)"
ls -l /dev/ptp* 2>&1
