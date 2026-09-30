"""D4 batch runner: each scenario repeated N times on the real Isaac, every run reset first, all attempts kept.

  python3 -m robosim_eval.batch [--scenarios normal,bypass,unreachable] [--repeats 3] [--out artifacts/d4]
                                [--config configs/baseline.yaml]
Each attempt is one `python3 -m robosim_eval.runner` process (the runner resets the scene through sim_control and checks
the reset against ground truth before it starts Nav2). Order: repeat 1 of every scenario, then repeat 2, ... so that a
slow drift over the batch does not load onto one scenario. The config and the scenario names are checked before the
first attempt. batch.json is rewritten before and after every attempt (state "running" until the batch closes out),
so a batch that is killed still leaves a record of every planned attempt; each attempt records its runner exit code,
its log and the run directory named on the runner's "run dir:" line.
Abort (plan doc A5: a stop that is not confirmed stops the batch and leaves an error): after runner exit 31 (a cancel
or stop was not confirmed), and after a runner that did not close out: killed by a signal, an exit code outside
0/10/11/20/30, or no merged result.json (no runner/evaluator verdict) in its run directory. The remaining attempts are
recorded as not run. Signals: the runner shares the batch's process group, so a terminal Ctrl-C reaches both once:
the running attempt cancels and closes out itself, the batch waits for it and then stops. SIGINT or SIGTERM sent to
the batch process alone (run_batch.sh's cap, `kill <pid>`) stops the batch after the current attempt, which runs to
its own end unsignalled. A runner exit 20 stops the batch as well. The report is then built from the saved records
only (robosim_eval.report, with batch.json).
Exit: 0 every planned attempt ran and closed out (whatever its verdict); 31 aborted (see above); 20 interrupted;
2 usage or config error (found before the first attempt: nothing run; or a runner refused to start: the rest not run);
30 the report could not be written (only when the batch would otherwise exit 0; batch.json says why).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from robosim_eval.config import load_config
from robosim_eval.report import main as report_main

REPO = Path(__file__).resolve().parents[1]
CLOSED_OUT = (0, 10, 11, 20, 30)   # runner exits after a confirmed close-out (runner.py _exit_code)


def check_config(config: Path, scenarios: Sequence[str]) -> Optional[str]:
    """Why the batch cannot start with this config and these scenarios, or None."""
    try:
        cfg = load_config(config)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return f"config error: {exc}"
    if cfg.run is None or cfg.sim is None:
        return f"config {config} has no run or no sim section (a batch drives the simulator)"
    unknown = [s for s in scenarios if s not in cfg.scenarios]
    if unknown:
        return f"unknown scenario(s) {unknown} (have: {sorted(cfg.scenarios)})"
    return None


def _run_dir_from_log(log: Path) -> Optional[Path]:
    try:
        with open(log, encoding="utf-8") as f:
            return next((Path(line[len("run dir:"):].strip()) for line in f if line.startswith("run dir:")), None)
    except OSError:
        return None


def _signal_name(num: int) -> str:
    try:
        return signal.Signals(num).name
    except ValueError:
        return f"signal {num}"


def close_out_problem(rc: int, run_dir: Optional[Path]) -> Tuple[int, Optional[str]]:
    """(0, None) when the attempt closed out; otherwise the batch status to abort with and why (plan doc A5)."""
    if rc == 2 and run_dir is None:
        return 2, "runner exit 2 (usage or config error) before it created a run directory"
    if rc == 31:
        return 31, "runner exit 31: a cancel or stop was not confirmed"
    if rc < 0:
        return 31, f"runner killed by {_signal_name(-rc)}: it did not close out, so its stop was never confirmed"
    if rc not in CLOSED_OUT:
        return 31, f"runner exit {rc} (not a close-out exit code): its stop was never confirmed"
    if run_dir is None:
        return 31, f"runner exit {rc} but its log names no run directory: close-out not confirmed"
    try:
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 31, f"runner exit {rc} but {run_dir.name}/result.json is missing or unreadable: close-out not confirmed"
    if not isinstance(result, dict) or "runner" not in result or "evaluator" not in result:
        return 31, (f"runner exit {rc} but {run_dir.name}/result.json has no merged runner verdict: "
                    "close-out not confirmed")
    if (result.get("runner") or {}).get("abort_batch"):
        return 31, f"runner exit {rc} but its result records abort_batch (a cancel or stop was not confirmed)"
    return 0, None


def _write_record(path: Path, rec: Dict[str, Any]) -> None:
    """Replace batch.json in one step, so a reader (or a kill) never sees half a record."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    os.replace(tmp, path)


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
    config = Path(a.config).resolve()   # the runner runs with cwd=REPO: hand it absolute paths
    problem = check_config(config, scenarios)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    batch_dir = Path(a.out).resolve() / f"batch-{time.strftime('%Y%m%d-%H%M%S')}"
    runs_dir = batch_dir / "runs"
    runs_dir.mkdir(parents=True)
    record_path = batch_dir / "batch.json"
    t_start = time.time()
    stop: Dict[str, Any] = {"why": None, "at": None}

    def on_signal(signum: int, _frame: Any) -> None:
        if stop["why"] is None:
            stop.update(why=signal.Signals(signum).name, at=round(time.time() - t_start, 1))

    previous = {s: signal.signal(s, on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        return _run(scenarios, a.repeats, config, batch_dir, runs_dir, record_path, stop, t_start)
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def _run(scenarios: List[str], repeats: int, config: Path, batch_dir: Path, runs_dir: Path, record_path: Path,
         stop: Dict[str, Any], t_start: float) -> int:
    plan = [(rep, sc) for rep in range(1, repeats + 1) for sc in scenarios]
    attempts: List[Dict[str, Any]] = [{"index": i, "scenario": sc, "repeat": rep, "exit": None, "note": "pending"}
                                      for i, (rep, sc) in enumerate(plan)]
    rec: Dict[str, Any] = {"scenarios": scenarios, "repeats": repeats, "config": str(config), "attempts": attempts,
                           "stopped_by": None, "stopped_at_s": None, "status": None, "state": "running",
                           "abort_index": None, "abort_reason": None, "report": None}
    _write_record(record_path, rec)
    status = 0
    for att in attempts:
        i, sc, rep = att["index"], att["scenario"], att["repeat"]
        if stop["why"] or status:
            att["note"] = f"not run: batch {'aborted' if status else 'interrupted'}"
            continue
        log = batch_dir / f"{i:02d}-{sc}-{rep}.txt"
        att.update(note="running", log=log.name)
        _write_record(record_path, rec)
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as f:
            # no start_new_session: the runner stays in this process group, so a terminal Ctrl-C reaches it once
            rc = subprocess.run([sys.executable, "-m", "robosim_eval.runner", "--scenario", sc, "--config", str(config),
                                 "--out", str(runs_dir)], stdout=f, stderr=subprocess.STDOUT, cwd=str(REPO)).returncode
        run_dir = _run_dir_from_log(log)
        att.pop("note")
        att.update(exit=rc, wall_s=round(time.time() - t0, 1), run_dir=str(run_dir) if run_dir else None)
        abort, why = close_out_problem(rc, run_dir)
        if abort:
            status = abort
            rec.update(abort_index=i, abort_reason=f"attempt {i} ({sc}, repeat {rep}): {why}")
        elif rc == 20 and not stop["why"]:
            stop.update(why="runner exit 20", at=round(time.time() - t_start, 1))
        _write_record(record_path, rec)   # before any echo: a closed terminal makes the echo fail with EIO
        print(json.dumps(att), flush=True)
        if abort:
            print(f"batch aborted: {rec['abort_reason']}", file=sys.stderr, flush=True)
    if stop["why"] and status == 0:
        status = 20
    rec.update(status=status, state={0: "completed", 20: "interrupted"}.get(status, "aborted"),
               stopped_by=stop["why"], stopped_at_s=stop["at"])
    _write_record(record_path, rec)
    try:
        report_rc = report_main([str(runs_dir), "--batch-json", str(record_path),
                                 "--title", f"RoboSim Eval batch {batch_dir.name}"])
        report_error = None if report_rc == 0 else f"report exit {report_rc}"
    except OSError as exc:
        report_error = f"{type(exc).__name__}: {exc}"
    if report_error is None:
        rec["report"] = {"written": True, "path": str(runs_dir / "report.html")}
    else:
        rec["report"] = {"written": False, "error": report_error}
        print(f"report not written: {report_error}", file=sys.stderr, flush=True)
        status = 30 if status == 0 else status
        rec["status"] = status
    _write_record(record_path, rec)
    print(f"batch dir: {batch_dir}")
    return status


if __name__ == "__main__":
    sys.exit(main())
