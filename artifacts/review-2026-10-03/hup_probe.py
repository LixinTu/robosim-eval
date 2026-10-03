"""Does closing the terminal (pty hangup) kill a process that run_scenario.sh-style `timeout` runs?

The stub stands in for the runner: it handles SIGINT and SIGTERM only (runner.py:131-132) and logs to a file.
A non-interactive bash runs a script whose last line is the timeout command, as run_scenario.sh does, as the session
leader with the pty as its controlling terminal; the parent then closes the pty master, as when the window is closed.
Usage: python3 hup_probe.py fg|bg   (fg = timeout --foreground, as now; bg = without it, as in v0.1.0)
"""
import os
import pty
import sys
import time

mode = sys.argv[1]
marker = f"/tmp/hup_probe_{mode}.txt"
script = f"/tmp/hup_probe_{mode}.sh"
stub = f"""
import signal, time
m = open({marker!r}, "w", buffering=1)
def h(s, f):
    m.write(f"handled {{signal.Signals(s).name}}\\n")
signal.signal(signal.SIGINT, h)
signal.signal(signal.SIGTERM, h)
m.write("started\\n")
time.sleep(8)
m.write("finished normally\\n")
"""
for p in (marker,):
    if os.path.exists(p):
        os.remove(p)
fg = "--foreground " if mode == "fg" else ""
with open(script, "w") as f:
    f.write("#!/usr/bin/env bash\n")
    f.write(f"timeout {fg}-s INT -k 120 1500 python3 -c \"$STUB\"\n")

pid, fd = pty.fork()
if pid == 0:
    os.environ["STUB"] = stub
    os.execvp("bash", ["bash", script])
time.sleep(2)
os.close(fd)                 # hang up, as when the console window is closed
_, status = os.waitpid(pid, 0)
time.sleep(9)                # the stub sleeps 8 s; give it time to finish if it survived
got = open(marker).read().strip().replace("\n", " | ") if os.path.exists(marker) else "no marker"
print(f"{mode}: bash wait status {status}; stub log: {got}")
