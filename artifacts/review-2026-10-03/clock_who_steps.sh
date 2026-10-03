#!/usr/bin/env bash
# Which agent steps the WSL wall clock back: systemd-timesyncd (NTP) or Hyper-V time sync? Samples the
# realtime-monotonic offset every 0.5 s and timesyncd's NTP packet count every 2 s, and prints each step (> 50 ms)
# with the packet count at that moment. Steps that land right after a packet-count increment are timesyncd's.
# Usage: bash -l clock_who_steps.sh <seconds>
python3 - "${1:-120}" <<'EOF'
import subprocess, sys, time
dur = float(sys.argv[1]); t_end = time.monotonic() + dur
def packets():
    out = subprocess.run(["timedatectl", "timesync-status"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "Packet count" in line:
            return int(line.split(":")[1])
    return None
prev = time.time() - time.monotonic(); pk = packets(); last_pk_t = time.monotonic(); steps = 0
print(f"{time.strftime('%H:%M:%S')} start, packet count {pk}", flush=True)
while time.monotonic() < t_end:
    time.sleep(0.5)
    off = time.time() - time.monotonic()
    if time.monotonic() - last_pk_t >= 2:
        new = packets(); last_pk_t = time.monotonic()
        if new != pk:
            print(f"{time.strftime('%H:%M:%S')} NTP packet count {pk} -> {new}", flush=True)
            pk = new
    if abs(off - prev) > 0.05:
        steps += 1
        print(f"{time.strftime('%H:%M:%S')} wall clock stepped {off - prev:+.3f} s (packet count {pk})", flush=True)
    prev = off
print(f"probe {dur:.0f} s: {steps} step(s), final packet count {pk}")
EOF
