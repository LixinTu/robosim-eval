#!/usr/bin/env bash
# Probe: how often and how far does the WSL wall clock get stepped (realtime - monotonic offset changes > 50 ms)?
# Usage: bash -l clock_probe.sh <seconds>
python3 - "${1:-90}" <<'EOF'
import sys, time
dur = float(sys.argv[1]); t_end = time.monotonic() + dur
prev = time.time() - time.monotonic(); steps = []
while time.monotonic() < t_end:
    time.sleep(0.5)
    off = time.time() - time.monotonic()
    if abs(off - prev) > 0.05:
        steps.append((time.strftime('%H:%M:%S'), off - prev))
        print(f"{time.strftime('%H:%M:%S')} wall clock stepped {off - prev:+.3f} s", flush=True)
    prev = off
print(f"probe {dur:.0f} s: {len(steps)} step(s), total {sum(s for _, s in steps):+.3f} s")
EOF
