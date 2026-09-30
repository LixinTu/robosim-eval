"""D4 batch runner: each scenario repeated N times on the real Isaac, every run reset first, all attempts kept.

  python3 -m robosim_eval.batch [--scenarios normal,bypass,unreachable] [--repeats 3] [--out artifacts/d4]
Each attempt is one `python3 -m robosim_eval.runner` process (the runner resets the scene through sim_control and checks
the reset against ground truth before it starts Nav2). Order: repeat 1 of every scenario, then repeat 2, ... so that a
slow drift over the batch does not load onto one scenario. A runner exit 31 (a cancel or stop was not confirmed) aborts
the rest of the batch, as plan doc A5 requires; the remaining attempts are recorded as not run. The report is then
built from the saved records only (robosim_eval.report). SIGINT/SIGTERM stop the batch after the current attempt
(which the runner closes out itself).
Exit: 0 all attempts ran (whatever their verdicts); 31 aborted by an unconfirmed stop; 20 interrupted; 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

from robosim_eval.report import main as report_main

REPO = Path(__file__).resolve().parents[1]


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RoboSim Eval D4 batch runner")
    p.add_argument("--scenarios", default="normal,bypass,unreachable")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--config", default=str(REPO / "configs" / "baseline.yaml"))
    p.add_argument("--out", default=str(REPO / "artifacts" / "d4"))
    a = p.parse_args(argv)
    scenarios = [s.strip() for s in a.scenarios.split(",") if s.strip()]
    if not scenarios or a.repeats < 1:
        print("need at least one scenario and one repeat", file=sys.stderr)
        return 2
    batch_dir = Path(a.out) / f"batch-{time.strftime('%Y%m%d-%H%M%S')}"
    runs_dir = batch_dir / "runs"
    runs_dir.mkdir(parents=True)
    stop = {"why": None}
    signal.signal(signal.SIGINT, lambda s, f: stop.update(why="SIGINT"))
    signal.signal(signal.SIGTERM, lambda s, f: stop.update(why="SIGTERM"))
    plan = [(rep, sc) for rep in range(1, a.repeats + 1) for sc in scenarios]
    log: List[dict] = []
    status = 0
    for i, (rep, sc) in enumerate(plan):
        if stop["why"] or status == 31:
            log.append({"index": i, "scenario": sc, "repeat": rep, "exit": None,
                        "note": f"not run: batch {'aborted' if status == 31 else 'interrupted'}"})
            continue
        t0 = time.time()
        with open(batch_dir / f"{i:02d}-{sc}-{rep}.txt", "w", encoding="utf-8") as f:
            rc = subprocess.run([sys.executable, "-m", "robosim_eval.runner", "--scenario", sc, "--config", a.config,
                                 "--out", str(runs_dir)], stdout=f, stderr=subprocess.STDOUT, cwd=str(REPO),
                                start_new_session=True).returncode
        entry = {"index": i, "scenario": sc, "repeat": rep, "exit": rc, "wall_s": round(time.time() - t0, 1)}
        log.append(entry)
        print(json.dumps(entry), flush=True)
        if rc == 31:
            status = 31
    if stop["why"] and status == 0:
        status = 20
    (batch_dir / "batch.json").write_text(json.dumps({"scenarios": scenarios, "repeats": a.repeats, "attempts": log,
                                                      "stopped_by": stop["why"], "status": status}, indent=2),
                                          encoding="utf-8")
    report_main([str(runs_dir), "--title", f"RoboSim Eval batch {batch_dir.name}"])
    print(f"batch dir: {batch_dir}")
    return status


if __name__ == "__main__":
    sys.exit(main())
