"""Does a terminal Ctrl-C reach a check that verify.sh runs under `timeout -s INT -k 10 <limit>` (no --foreground)?

A non-interactive bash runs two checks the way verify.sh's run_check does; the parent types ^C into the pty 2 s into
the first one. The stub logs whether it got SIGINT. Usage: python3 verify_ctrlc_probe.py
"""
import os
import pty
import select
import time

marker = "/tmp/verify_ctrlc_probe.txt"
script = "/tmp/verify_ctrlc_probe.sh"
stub = f"""
import signal, sys, time
m = open({marker!r}, "a", buffering=1)
def h(s, f):
    m.write("stub got SIGINT\\n"); sys.exit(130)
signal.signal(signal.SIGINT, h)
time.sleep(6)
m.write("stub finished normally\\n")
"""
if os.path.exists(marker):
    os.remove(marker)
with open(script, "w") as f:
    f.write("#!/usr/bin/env bash\nset -uo pipefail\n")
    for n in (1, 2):
        f.write(f'echo "check{n} start" >> {marker}\n')
        f.write(f'(cd /tmp && timeout -s INT -k 10 600 python3 -c "$STUB") > /tmp/verify_ctrlc_c{n}.log 2>&1\n')
        f.write(f'echo "check{n} rc=$?" >> {marker}\n')

t0 = time.monotonic()
pid, fd = pty.fork()
if pid == 0:
    os.environ["STUB"] = stub
    os.execvp("bash", ["bash", script])
time.sleep(2)
os.write(fd, b"\x03")            # Ctrl-C typed in the terminal
status = None
while time.monotonic() - t0 < 30:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try:
            os.read(fd, 1024)
        except OSError:
            pass
    done, status = os.waitpid(pid, os.WNOHANG)
    if done:
        break
print(f"bash wait status {status}, {time.monotonic() - t0:.1f} s after start")
print(open(marker).read().strip().replace("\n", " | "))
