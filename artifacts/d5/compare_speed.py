"""D5 operation 3: compare runs of normal and normal_slow from their saved records only (no ROS needed).

  python3 artifacts/d5/compare_speed.py <runs_dir> [<runs_dir> ...]   -> a markdown table on stdout
Per run (Nav2 SUCCEEDED or not): verdicts, ground-truth arrival error, the Nav2 max_vel_x in effect, time from goal
acceptance to the first odometry speed > 0.05 m/s, the drive phase (from then to the Nav2 result), peak and mean
moving linear speed, peak angular speed, path length, and Nav2's recovery count. Speeds and positions are the ideal
odometry rows of trajectory.csv inside [accept, result] (simulation time). The acceptance time is the one the offline
analysis took from the bag (result.json timing): the runner's own value was 1.1-2.1 s stale before 9ae722b.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import List, Optional

MOVING_MPS = 0.05


def row(run_dir: Path) -> Optional[List[str]]:
    try:
        r = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    run = r.get("runner") or {}
    acc = (r.get("timing") or {}).get("sim_time_at_accept_s", run.get("accept_sim"))
    term = run.get("terminal_sim")
    params = (run.get("nav2_params") or {}).get("changes") or []
    in_effect = ", ".join(f"{c['param']}={c.get('in_effect')}" for c in params) or "vendor default (0.8)"
    cells = [run_dir.name, r.get("validation_status"), r.get("task_outcome"), r.get("safety_status"),
             (run.get("terminal") or {}).get("name"), in_effect]
    err = (r.get("evaluator") or {}).get("arrival_error_m")
    cells.append("" if err is None else f"{err:.3f}")
    pts = []
    traj = run_dir / "trajectory.csv"
    if acc is not None and term is not None and traj.exists():
        with traj.open(encoding="utf-8") as f:
            for p in csv.DictReader(f):
                if p["source"].startswith("ideal odometry") and acc <= float(p["sim_stamp_s"]) <= term:
                    pts.append((float(p["sim_stamp_s"]), float(p["lin_speed"]), float(p["x"]), float(p["y"]),
                                abs(float(p["ang_speed"]))))
    moving = [p for p in pts if p[1] > MOVING_MPS]
    if moving:
        first = moving[0][0]
        seg = [p for p in pts if p[0] >= first]
        length = sum(((b[2] - a[2]) ** 2 + (b[3] - a[3]) ** 2) ** 0.5 for a, b in zip(seg, seg[1:]))
        cells += [f"{first - acc:.1f}", f"{term - first:.1f}", f"{max(p[1] for p in pts):.3f}",
                  f"{sum(p[1] for p in moving) / len(moving):.3f}", f"{max(p[4] for p in pts):.3f}", f"{length:.2f}"]
    else:
        cells += ["", "", "", "", "", ""]
    cells.append(str((r.get("nav2_raw") or {}).get("recoveries", "")))
    return [str(c) for c in cells]


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    head = ["run", "validation", "outcome", "safety", "Nav2", "max_vel_x in effect", "arrival error m (GT)",
            "first move after accept s", "drive phase s", "peak m/s", "mean moving m/s", "peak rad/s", "path m",
            "recoveries"]
    print("| " + " | ".join(head) + " |")
    print("|" + " --- |" * len(head))
    for d in argv:
        for run_dir in sorted(p for p in Path(d).iterdir() if p.is_dir()):
            cells = row(run_dir)
            if cells:
                print("| " + " | ".join(cells) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
