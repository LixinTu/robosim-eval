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
recorded as not run. Signals: the runner runs in its own session, so no signal from the terminal reaches it directly
(not a Ctrl-C, SIGQUIT or SIGTSTP, nor the hang-up of a closed console window). A SIGINT to the batch (a terminal
Ctrl-C) is forwarded once to the running attempt, which cancels and closes out itself; the batch waits for it and then
stops. SIGTERM (run_batch.sh's cap, `kill <pid>`) and SIGHUP (the console window was closed) stop the batch after the
current attempt, which runs to its own end unsignalled. A runner exit 20 stops the batch as well. The report is then
built from the saved records only (robosim_eval.report, with batch.json). The console output is only a copy of those
records: once the terminal is gone (EIO), the batch stops echoing, records the error (batch.json echo_error) and
still closes out.
Exit: 0 every planned attempt ran and closed out (whatever its verdict); 31 aborted (see above); 20 interrupted;
2 usage or config error (found before the first attempt: nothing run; or a runner refused to start: the rest not run);
30 the report could not be written (only when the batch would otherwise exit 0; batch.json says why).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Sequence, Set, Tuple

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


class _Signals:
    """Why the batch stops (the first reason it got) and the one SIGINT it owes the running attempt.

    Every handled signal stops the batch after the current attempt. Only SIGINT (a terminal Ctrl-C, which also
    arrives a second time as timeout --foreground's copy) is forwarded to the attempt, once, including when it came
    while the runner was being started; SIGTERM and SIGHUP leave the attempt to run to its own end."""

    HANDLED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

    def __init__(self, t_start: float) -> None:
        self.t_start = t_start
        self.why: Optional[str] = None
        self.at: Optional[float] = None
        self.interrupted = False
        self.forwarded = False
        self.proc: Optional[subprocess.Popen] = None

    def stop(self, why: str) -> None:
        if self.why is None:
            self.why, self.at = why, round(time.time() - self.t_start, 1)

    def handle(self, signum: int, _frame: Any) -> None:
        self.stop(signal.Signals(signum).name)
        if signum == signal.SIGINT:
            self.interrupted = True
            self._forward()

    def attach(self, proc: subprocess.Popen) -> None:
        self.forwarded = False
        self.proc = proc
        self._forward()   # a Ctrl-C that came while the runner was being started

    def detach(self) -> None:
        self.proc = None

    def _forward(self) -> None:
        if self.interrupted and self.proc is not None and not self.forwarded:
            self.forwarded = True
            self.proc.send_signal(signal.SIGINT)   # not once it has been reaped (Popen.send_signal polls first)


def _point_at_devnull(stream: Any) -> None:
    """Point the fd behind a stream that can no longer be written at /dev/null, so the text left in its buffer is
    flushed there at exit instead of failing again and turning the batch's exit status into Python's 120."""
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):   # no fd behind it (io.UnsupportedOperation is both of the last two)
        return
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, fd)
    finally:
        os.close(null)


class _Echo:
    """The batch's console output, which is only a copy: every record is on disk before it is echoed.

    A stream whose write fails (the console window was closed: EIO; a closed pipe) is not written again and is pointed
    at /dev/null; the first such error is recorded in batch.json (echo_error) at once."""

    def __init__(self, rec: Dict[str, Any], record_path: Path) -> None:
        self.rec, self.record_path = rec, record_path
        self.lost: Set[str] = set()

    def __call__(self, text: str, err: bool = False) -> None:
        name = "stderr" if err else "stdout"
        if name in self.lost:
            return
        stream = getattr(sys, name)
        try:
            print(text, file=stream, flush=True)
        except OSError as exc:
            self.lost.add(name)
            _point_at_devnull(stream)
            if self.rec["echo_error"] is None:
                self.rec["echo_error"] = f"{name}: {type(exc).__name__}: {exc}"
                _write_record(self.record_path, self.rec)


def _run_attempt(cmd: List[str], log: IO[str], sig: _Signals) -> int:
    """Run one runner process to its end; its exit code (negative: killed by that signal).

    Its own session: the terminal's signals never reach the runner directly, only the SIGINT the batch forwards."""
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO), start_new_session=True)
    sig.attach(proc)
    try:
        return proc.wait()
    finally:
        sig.detach()


def _write_report(runs_dir: Path, record_path: Path, title: str, echo: _Echo) -> Optional[str]:
    """Build the report from the saved records: None when it was written, otherwise why not. The report's console
    output is captured and then echoed, so a terminal that is gone never reads as a report that was not written."""
    out, err = io.StringIO(), io.StringIO()
    error: Optional[str] = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            report_rc = report_main([str(runs_dir), "--batch-json", str(record_path), "--title", title])
        if report_rc != 0:
            why = err.getvalue().strip()
            error = f"report exit {report_rc}" + (f": {why}" if why else "")
    except OSError as exc:
        error = f"{type(exc).__name__}: {exc}"
    for line in out.getvalue().splitlines():
        echo(line)
    for line in err.getvalue().splitlines():
        echo(line, err=True)
    return error


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
    sig = _Signals(time.time())
    previous = {s: signal.signal(s, sig.handle) for s in _Signals.HANDLED}
    try:
        return _run(scenarios, a.repeats, config, batch_dir, runs_dir, record_path, sig)
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def _run(scenarios: List[str], repeats: int, config: Path, batch_dir: Path, runs_dir: Path, record_path: Path,
         sig: _Signals) -> int:
    plan = [(rep, sc) for rep in range(1, repeats + 1) for sc in scenarios]
    attempts: List[Dict[str, Any]] = [{"index": i, "scenario": sc, "repeat": rep, "exit": None, "note": "pending"}
                                      for i, (rep, sc) in enumerate(plan)]
    rec: Dict[str, Any] = {"scenarios": scenarios, "repeats": repeats, "config": str(config), "attempts": attempts,
                           "stopped_by": None, "stopped_at_s": None, "status": None, "state": "running",
                           "abort_index": None, "abort_reason": None, "echo_error": None, "report": None}
    _write_record(record_path, rec)
    echo = _Echo(rec, record_path)
    status = 0
    for att in attempts:
        i, sc, rep = att["index"], att["scenario"], att["repeat"]
        if sig.why or status:
            att["note"] = f"not run: batch {'aborted' if status else 'interrupted'}"
            continue
        log = batch_dir / f"{i:02d}-{sc}-{rep}.txt"
        att.update(note="running", log=log.name)
        _write_record(record_path, rec)
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as f:
            rc = _run_attempt([sys.executable, "-m", "robosim_eval.runner", "--scenario", sc, "--config", str(config),
                               "--out", str(runs_dir)], f, sig)
        run_dir = _run_dir_from_log(log)
        att.pop("note")
        att.update(exit=rc, wall_s=round(time.time() - t0, 1), run_dir=str(run_dir) if run_dir else None)
        abort, why = close_out_problem(rc, run_dir)
        if abort:
            status = abort
            rec.update(abort_index=i, abort_reason=f"attempt {i} ({sc}, repeat {rep}): {why}")
        elif rc == 20:
            sig.stop("runner exit 20")
        _write_record(record_path, rec)   # before any echo: a closed terminal makes the echo fail with EIO
        echo(json.dumps(att))
        if abort:
            echo(f"batch aborted: {rec['abort_reason']}", err=True)
    if sig.why and status == 0:
        status = 20
    rec.update(status=status, state={0: "completed", 20: "interrupted"}.get(status, "aborted"),
               stopped_by=sig.why, stopped_at_s=sig.at)
    _write_record(record_path, rec)
    report_error = _write_report(runs_dir, record_path, f"RoboSim Eval batch {batch_dir.name}", echo)
    if report_error is None:
        rec["report"] = {"written": True, "path": str(runs_dir / "report.html")}
    else:
        rec["report"] = {"written": False, "error": report_error}
        status = 30 if status == 0 else status
        rec["status"] = status
    _write_record(record_path, rec)
    if report_error is not None:
        echo(f"report not written: {report_error}", err=True)
    echo(f"batch dir: {batch_dir}")
    return status


if __name__ == "__main__":
    sys.exit(main())
