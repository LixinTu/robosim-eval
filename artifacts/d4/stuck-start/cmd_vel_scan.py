"""Scratch: for every real run, how long the controller kept the minimum rotation sample (0, +-0.0368 rad/s) at the start."""
import datetime as dt, glob, json, os
def t(s): return dt.datetime.fromisoformat(s)
print("run | contacts | first cmd | min-rotation phase wall s | first linear>0.1 after first cmd wall s | recoveries")
for d in sorted(glob.glob("/mnt/d/RoboSim-Eval/artifacts/**/*-2026093*-*/cmd_vel.txt", recursive=True)):
    d = os.path.dirname(d)
    ev = open(os.path.join(d, "events.jsonl")).read() if os.path.exists(os.path.join(d, "events.jsonl")) else ""
    contacts = '"contacts_installed"' in ev
    cmds = []
    for line in open(os.path.join(d, "cmd_vel.txt")):
        parts = line.split()
        if len(parts) != 2: continue
        v = [float(x) for x in parts[1].split(",")]
        cmds.append((t(parts[0]), v[0], v[5]))
    if not cmds: continue
    t0 = cmds[0][0]
    minrot_end = None
    for ts, lx, az in cmds:
        if abs(lx) < 1e-9 and abs(abs(az) - 0.7 / 19) < 1e-6 or (abs(lx) < 1e-9 and az == 0.0):
            minrot_end = ts
        else:
            break
    first_lin = next((ts for ts, lx, az in cmds if lx > 0.1), None)
    rec = None
    try:
        rec = (json.load(open(os.path.join(d, "result.json"))).get("nav2_raw") or {}).get("recoveries")
    except Exception:
        pass
    print(f"{os.path.relpath(d, '/mnt/d/RoboSim-Eval/artifacts')} | {contacts} | {t0.time()} | "
          f"{(minrot_end - t0).total_seconds() if minrot_end else 0:.1f} | "
          f"{(first_lin - t0).total_seconds() if first_lin else None} | {rec}")
