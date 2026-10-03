#!/usr/bin/env bash
# Read-only: what systemd-timesyncd has logged this boot, its poll state, and kernel time-set messages.
journalctl -b -u systemd-timesyncd --no-pager 2>&1 | tail -n 25
echo "--- timesync status"
timedatectl timesync-status 2>&1 | head -20
echo "--- kernel: time set / hv_utils"
journalctl -k -b --no-pager 2>/dev/null | grep -i -E 'time.*(set|jump|step)|hv_utils|timesync' | tail -n 10
