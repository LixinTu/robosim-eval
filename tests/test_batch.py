"""Tests for the D4 batch runner (robosim_eval.batch) and its wrapper scripts/wsl/run_batch.sh.

No test here starts the real runner, ROS or the simulator:
- the fixed-input tests replace subprocess.run inside the batch module (no child process at all);
- the terminal tests copy run_batch.sh and the package into a temp tree whose robosim_eval/runner.py is a stub and
  whose ros_env.sh / dds_env.sh are empty, then drive `bash run_batch.sh` on a pseudo-terminal (Python pty).
"""
from __future__ import annotations

import json
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pytest

from robosim_eval import batch

CONFIG = batch.REPO / "configs" / "baseline.yaml"


def merged_result(scenario: str, validation: str = "pass", abort_batch: bool = False) -> dict:
    return {"execution_status": "completed", "task_outcome": "reached", "safety_status": "pass",
            "data_status": "complete", "validation_status": validation,
            "verdict_reasons": {"fail": [], "inconclusive": [], "warnings": []},
            "evaluator": {"arrival_error_m": 0.2, "disallowed_contacts": []},
            "runner": {"scenario": scenario, "abort_batch": abort_batch}}


class FakeRunner:
    """Stands in for subprocess.run inside robosim_eval.batch: writes what a runner would, starts nothing.

    Each spec (by call order, the last one repeats): rc; result 'merged' | 'analyzer' | None (no result.json);
    mkdir (False: the runner exits before it creates a run dir); abort_batch; hook (called before returning)."""

    def __init__(self, *specs: dict) -> None:
        self.specs = specs or ({"rc": 0},)
        self.calls: List[dict] = []

    def __call__(self, cmd: List[str], **kw) -> subprocess.CompletedProcess:
        i = len(self.calls)
        self.calls.append({"cmd": cmd, "kw": kw})
        spec = {"rc": 0, "result": "merged", "mkdir": True, **self.specs[min(i, len(self.specs) - 1)]}
        scenario, out = cmd[cmd.index("--scenario") + 1], Path(cmd[cmd.index("--out") + 1])
        f = kw["stdout"]
        if spec["mkdir"]:
            run_dir = out / f"{scenario}-20260930-10{i:04d}"
            run_dir.mkdir(parents=True)
            f.write(f"run dir: {run_dir}\n")
            if spec["result"] == "merged":
                res = merged_result(scenario, abort_batch=spec.get("abort_batch", False))
                (run_dir / "result.json").write_text(json.dumps(res), encoding="utf-8")
            elif spec["result"] == "analyzer":
                res = {k: v for k, v in merged_result(scenario).items() if k not in ("runner", "evaluator")}
                (run_dir / "result.json").write_text(json.dumps(res), encoding="utf-8")
        else:
            f.write(f"config has no run section or no scenario {scenario!r}\n")
        if spec.get("hook"):
            spec["hook"]()
        return subprocess.CompletedProcess(cmd, spec["rc"])


def run_batch(tmp_path: Path, monkeypatch, fake: FakeRunner, scenarios: str = "normal,bypass,unreachable",
              repeats: int = 2, config: Path = CONFIG) -> tuple:
    monkeypatch.setattr(batch.subprocess, "run", fake)
    rc = batch.main(["--scenarios", scenarios, "--repeats", str(repeats), "--config", str(config),
                     "--out", str(tmp_path)])
    dirs = sorted(tmp_path.glob("batch-*"))
    rec = json.loads((dirs[0] / "batch.json").read_text(encoding="utf-8")) if dirs else None
    return rc, rec, (dirs[0] if dirs else None)


def send_to_batch(signum: int) -> Callable[[], None]:
    """What the kernel does when the signal arrives during the attempt: call the handler the batch installed."""
    def hook() -> None:
        handler = signal.getsignal(signum)
        assert callable(handler) and handler is not signal.default_int_handler
        handler(signum, None)
    return hook


def test_all_attempts_close_out_exit_0_and_every_attempt_is_recorded(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 0}, {"rc": 10}, {"rc": 11}, {"rc": 30})
    rc, rec, bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 0 and len(fake.calls) == 6
    assert rec["state"] == "completed" and rec["status"] == 0 and rec["stopped_by"] is None
    assert [a["exit"] for a in rec["attempts"]] == [0, 10, 11, 30, 30, 30]
    assert all(Path(a["run_dir"]).parent == bdir / "runs" and (bdir / a["log"]).exists() for a in rec["attempts"])
    assert rec["report"]["written"] is True and (bdir / "runs" / "report.html").exists()


def test_runner_is_started_in_the_batch_process_group_with_absolute_paths(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 0})
    monkeypatch.chdir(tmp_path)
    rc, _rec, _bdir = run_batch(Path("."), monkeypatch, fake, scenarios="normal", repeats=1)
    assert rc == 0
    call = fake.calls[0]
    # sharing the process group is what lets a terminal Ctrl-C reach the running attempt exactly once
    assert not call["kw"].get("start_new_session") and call["kw"].get("process_group") is None
    cmd = call["cmd"]
    assert Path(cmd[cmd.index("--out") + 1]).is_absolute() and Path(cmd[cmd.index("--config") + 1]).is_absolute()


def test_runner_exit_31_aborts_the_rest_of_the_batch(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 0}, {"rc": 31})
    rc, rec, bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 31 and len(fake.calls) == 2
    assert rec["state"] == "aborted" and rec["status"] == 31 and rec["abort_index"] == 1
    assert "runner exit 31" in rec["abort_reason"]
    assert [a["exit"] for a in rec["attempts"]] == [0, 31, None, None, None, None]
    assert all(a["note"] == "not run: batch aborted" for a in rec["attempts"][2:])
    html = (bdir / "runs" / "report.html").read_text(encoding="utf-8")
    assert "Batch aborted" in html and html.count("not run (batch aborted)") == 4


@pytest.mark.parametrize("spec, words", [
    ({"rc": -9, "result": None}, "SIGKILL"),                  # killed (OOM, kill -9): no result.json
    ({"rc": -11, "result": "analyzer"}, "SIGSEGV"),           # native crash after the offline analysis
    ({"rc": 1, "result": "analyzer"}, "exit 1"),              # uncaught exception in the teardown
    ({"rc": 11, "result": None}, "result.json is missing"),   # a clean-looking exit without its result
    ({"rc": 0, "result": "analyzer"}, "no merged runner verdict"),
    ({"rc": 30, "abort_batch": True}, "abort_batch"),         # the runner flagged an unconfirmed stop
    ({"rc": 0, "mkdir": False}, "names no run directory"),
])
def test_runner_that_did_not_close_out_aborts_like_31(tmp_path: Path, monkeypatch, spec: dict, words: str):
    fake = FakeRunner(spec)
    rc, rec, _bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 31 and len(fake.calls) == 1
    assert rec["state"] == "aborted" and words in rec["abort_reason"]
    assert all(a["note"] == "not run: batch aborted" for a in rec["attempts"][1:])


def test_runner_refusing_to_start_mid_batch_stops_it_with_2(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 0}, {"rc": 2, "mkdir": False})
    rc, rec, bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 2 and len(fake.calls) == 2 and rec["state"] == "aborted"
    assert rec["attempts"][1]["run_dir"] is None and "before it created a run directory" in rec["abort_reason"]
    assert "no run dir (runner exit 2)" in (bdir / "runs" / "report.html").read_text(encoding="utf-8")


def test_sigint_during_an_attempt_lets_it_close_out_then_stops_with_20(tmp_path: Path, monkeypatch):
    before = signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)
    fake = FakeRunner({"rc": 20, "hook": send_to_batch(signal.SIGINT)})
    rc, rec, bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 20 and len(fake.calls) == 1
    assert rec["state"] == "interrupted" and rec["stopped_by"] == "SIGINT" and rec["status"] == 20
    assert rec["attempts"][0]["exit"] == 20 and rec["attempts"][0]["run_dir"]
    assert all(a["note"] == "not run: batch interrupted" for a in rec["attempts"][1:])
    assert "Batch interrupted" in (bdir / "runs" / "report.html").read_text(encoding="utf-8")
    assert (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)) == before   # handlers restored


def test_sigterm_to_the_batch_alone_stops_after_the_current_attempt(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 0, "hook": send_to_batch(signal.SIGTERM)})
    rc, rec, _bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 20 and len(fake.calls) == 1 and rec["stopped_by"] == "SIGTERM"
    assert rec["attempts"][0]["exit"] == 0 and rec["stopped_at_s"] is not None


def test_runner_exit_20_without_a_batch_signal_still_stops_the_batch(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 20})
    rc, rec, _bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 20 and len(fake.calls) == 1 and rec["stopped_by"] == "runner exit 20"


def test_abort_takes_precedence_over_an_interrupt(tmp_path: Path, monkeypatch):
    fake = FakeRunner({"rc": 31, "hook": send_to_batch(signal.SIGINT)})
    rc, rec, _bdir = run_batch(tmp_path, monkeypatch, fake)
    assert rc == 31 and rec["state"] == "aborted" and rec["stopped_by"] == "SIGINT"
    assert all(a["note"] == "not run: batch aborted" for a in rec["attempts"][1:])


@pytest.mark.parametrize("scenarios, config", [("normal,bypas", CONFIG), ("normal", Path("no/such/config.yaml"))])
def test_usage_errors_are_found_before_anything_runs(tmp_path: Path, monkeypatch, scenarios: str, config: Path):
    fake = FakeRunner({"rc": 0})
    rc, rec, bdir = run_batch(tmp_path, monkeypatch, fake, scenarios=scenarios, config=config)
    assert rc == 2 and fake.calls == [] and bdir is None and rec is None


def test_batch_record_is_on_disk_before_each_attempt(tmp_path: Path, monkeypatch):
    """A batch that is killed mid-attempt still leaves a record naming the attempt in progress."""
    seen: Dict[str, object] = {}

    def look() -> None:
        (bdir,) = tmp_path.glob("batch-*")
        rec = json.loads((bdir / "batch.json").read_text(encoding="utf-8"))
        seen.update(state=rec["state"], notes=[a.get("note") for a in rec["attempts"]])

    fake = FakeRunner({"rc": 0, "hook": look}, {"rc": 0})
    rc, _rec, _bdir = run_batch(tmp_path, monkeypatch, fake, scenarios="normal,bypass", repeats=1)
    assert rc == 0 and seen["state"] == "running" and seen["notes"] == ["running", "pending"]


class GoneTerminal:
    """stdout of a batch whose terminal window was closed: every write fails with EIO."""

    def write(self, _text: str) -> int:
        raise OSError(5, "Input/output error")

    def flush(self) -> None:
        raise OSError(5, "Input/output error")


def test_attempt_is_recorded_before_it_is_echoed_to_the_terminal(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", GoneTerminal())
    monkeypatch.setattr(sys, "stderr", GoneTerminal())
    with pytest.raises(OSError):
        run_batch(tmp_path, monkeypatch, FakeRunner({"rc": 31}), scenarios="normal,bypass", repeats=1)
    (bdir,) = tmp_path.glob("batch-*")
    rec = json.loads((bdir / "batch.json").read_text(encoding="utf-8"))
    assert rec["attempts"][0]["exit"] == 31 and "note" not in rec["attempts"][0]
    assert rec["abort_index"] == 0 and "runner exit 31" in rec["abort_reason"]


def test_report_that_cannot_be_written_is_an_error_exit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(batch, "report_main", lambda argv: 2)
    rc, rec, _bdir = run_batch(tmp_path, monkeypatch, FakeRunner({"rc": 0}), scenarios="normal", repeats=1)
    assert rc == 30 and rec["status"] == 30 and rec["report"]["written"] is False


def test_report_io_error_is_an_error_exit_and_keeps_an_abort(tmp_path: Path, monkeypatch):
    def broken(argv):
        raise OSError("disk full")
    monkeypatch.setattr(batch, "report_main", broken)
    rc, rec, _bdir = run_batch(tmp_path, monkeypatch, FakeRunner({"rc": 31}), scenarios="normal", repeats=1)
    assert rc == 31 and "disk full" in rec["report"]["error"]


# ---- the wrapper on a terminal ---------------------------------------------------------------------------------------

STUB_RUNNER = '''"""Stub runner for tests/test_batch.py: no ROS, no simulator; counts the signals it receives."""
import json, os, signal, sys, time
from pathlib import Path

args = sys.argv[1:]
scenario, out = args[args.index("--scenario") + 1], Path(args[args.index("--out") + 1])
marks = Path(os.environ["STUB_MARKS"])
n = len(list(marks.glob("started-*")))
run_dir = out / f"{scenario}-20260930-{100000 + n}"
run_dir.mkdir(parents=True)
print(f"run dir: {run_dir}", flush=True)
got = []
signal.signal(signal.SIGINT, lambda s, f: got.append("SIGINT"))
signal.signal(signal.SIGTERM, lambda s, f: got.append("SIGTERM"))
(marks / f"started-{n}").write_text(json.dumps({"pid": os.getpid(), "ppid": os.getppid()}))
deadline = time.monotonic() + float(os.environ["STUB_RUN_S"])
while time.monotonic() < deadline and not got:
    time.sleep(0.05)
if got:
    time.sleep(1.0)   # the close-out; a second signal would be counted here
res = {"execution_status": "interrupted" if got else "completed", "task_outcome": "unknown" if got else "reached",
       "safety_status": "pass", "data_status": "complete", "validation_status": "inconclusive" if got else "pass",
       "verdict_reasons": {"fail": [], "inconclusive": [], "warnings": []},
       "evaluator": {"arrival_error_m": 0.2, "disallowed_contacts": []},
       "runner": {"scenario": scenario, "abort_batch": False, "stub": True}}
(run_dir / "result.json").write_text(json.dumps(res))
(marks / f"signals-{n}").write_text(json.dumps(got))
sys.exit(20 if got else 0)
'''

needs_terminal = pytest.mark.skipif(sys.platform != "linux" or shutil.which("timeout") is None
                                    or shutil.which("bash") is None, reason="needs Linux, bash and GNU timeout")


def stub_tree(tmp_path: Path, cap_s: Optional[int] = None) -> Path:
    """A copy of the checkout's run_batch.sh and package in which the runner is a stub and the ROS env is empty."""
    t = tmp_path / "tree"
    (t / "scripts" / "wsl").mkdir(parents=True)
    (t / "configs").mkdir()
    script = (batch.REPO / "scripts" / "wsl" / "run_batch.sh").read_text(encoding="utf-8")
    if "REPO=/mnt/d/RoboSim-Eval" in script:   # it would run the main checkout's real runner on the live simulator
        pytest.fail("run_batch.sh hard-codes the main checkout; refusing to run it")
    if cap_s is not None:
        assert script.count(" 14400 ") == 1
        script = script.replace(" 14400 ", f" {cap_s} ")
    (t / "scripts" / "wsl" / "run_batch.sh").write_text(script, encoding="utf-8")
    for env_script in ("ros_env.sh", "dds_env.sh"):
        (t / "scripts" / "wsl" / env_script).write_text("return 0\n", encoding="utf-8")
    shutil.copy(CONFIG, t / "configs" / "baseline.yaml")
    shutil.copytree(batch.REPO / "robosim_eval", t / "robosim_eval", ignore=shutil.ignore_patterns("__pycache__"))
    (t / "robosim_eval" / "runner.py").write_text(STUB_RUNNER, encoding="utf-8")
    (t / "marks").mkdir()
    return t


def on_terminal(t: Path, run_s: float, act: Callable[[Path, int], bool], limit_s: float = 60.0) -> tuple:
    """Run `bash run_batch.sh` as the session leader of a new pseudo-terminal (as wsl.exe runs it from a console).

    act(marks_dir, terminal_fd) is polled while the output is drained; it returns True once it has acted."""
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(t), "STUB_MARKS": str(t / "marks"),
           "STUB_RUN_S": str(run_s)}
    argv = ["bash", str(t / "scripts" / "wsl" / "run_batch.sh"), "--scenarios", "normal,bypass", "--repeats", "2",
            "--out", str(t / "out")]
    pid, fd = pty.fork()
    if pid == 0:   # child: exec or die, never return into pytest
        try:
            os.execvpe(argv[0], argv, env)
        finally:
            os._exit(127)
    out, acted, t0 = b"", False, time.monotonic()
    try:
        while True:
            if time.monotonic() - t0 > limit_s:
                os.killpg(pid, signal.SIGKILL)   # only the tree this test started
                pytest.fail(f"run_batch.sh still running after {limit_s} s; output so far:\n{out.decode(errors='replace')}")
            if not acted:
                acted = act(t / "marks", fd)
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:   # EIO: every holder of the terminal has exited
                    break
                if not chunk:
                    break
                out += chunk
    finally:
        os.close(fd)
    _pid, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode(errors="replace")


def read_marks(t: Path) -> tuple:
    started = sorted((t / "marks").glob("started-*"))
    signals = [json.loads(p.read_text()) for p in sorted((t / "marks").glob("signals-*"))]
    (bdir,) = (t / "out").glob("batch-*")
    return len(started), signals, json.loads((bdir / "batch.json").read_text(encoding="utf-8")), bdir


@needs_terminal
def test_terminal_ctrl_c_reaches_the_attempt_once_and_the_batch_exits_20(tmp_path: Path):
    t = stub_tree(tmp_path)

    def ctrl_c(marks: Path, terminal: int) -> bool:
        if not (marks / "started-0").exists():
            return False
        os.write(terminal, b"\x03")   # the terminal's interrupt character: SIGINT to its foreground process group
        return True

    rc, out = on_terminal(t, 30.0, ctrl_c)
    started, signals, rec, bdir = read_marks(t)
    assert rc == 20, out
    assert started == 1 and signals == [["SIGINT"]]          # the running attempt got exactly one SIGINT
    assert rec["state"] == "interrupted" and rec["stopped_by"] == "SIGINT"
    assert rec["attempts"][0]["exit"] == 20 and all(a["note"] == "not run: batch interrupted"
                                                     for a in rec["attempts"][1:])
    assert "Batch interrupted" in (bdir / "runs" / "report.html").read_text(encoding="utf-8")


@needs_terminal
def test_sigterm_to_the_batch_lets_the_attempt_finish_unsignalled(tmp_path: Path):
    t = stub_tree(tmp_path)

    def term_batch(marks: Path, _terminal: int) -> bool:
        if not (marks / "started-0").exists():
            return False
        os.kill(json.loads((marks / "started-0").read_text())["ppid"], signal.SIGTERM)   # the batch we started
        return True

    rc, out = on_terminal(t, 3.0, term_batch)
    started, signals, rec, _bdir = read_marks(t)
    assert rc == 20, out
    assert started == 1 and signals == [[]] and rec["attempts"][0]["exit"] == 0 and rec["stopped_by"] == "SIGTERM"


@needs_terminal
def test_cap_stops_the_batch_after_the_attempt_and_keeps_its_exit_code(tmp_path: Path):
    t = stub_tree(tmp_path, cap_s=3)   # the first attempt starts well within 3 s and runs 6 s: the cap hits it
    rc, out = on_terminal(t, 6.0, lambda marks, terminal: True)
    started, signals, rec, bdir = read_marks(t)
    assert rc == 20, out                                     # the batch's own code, not timeout's 124
    assert started == 1 and signals == [[]] and rec["attempts"][0]["exit"] == 0
    assert rec["state"] == "interrupted" and rec["stopped_by"] == "SIGTERM"
    assert (bdir / "runs" / "report.html").exists()


# ---- evidence script: artifacts/d4/stuck-start/run_bag_scans.sh (report_batch-11) ------------------------------------

@needs_terminal
def test_bag_scan_covers_every_run_dir_the_cmd_vel_scan_covers(tmp_path: Path):
    """Both halves use cmd_vel_scan.py's rule: dirs named <scenario>-2026093*-* holding a cmd_vel.txt, at any depth."""
    here = tmp_path / "artifacts" / "d4" / "stuck-start"
    here.mkdir(parents=True)
    shutil.copy(batch.REPO / "artifacts" / "d4" / "stuck-start" / "run_bag_scans.sh", here)
    (here / "plan_heading.py").write_text("import sys\nfor d in sys.argv[1:]:\n    print('PLAN', d)\n", "utf-8")
    (here / "cmd_vel_scan.py").write_text("print('run | x')\nprint('a | 1')\nprint('b | 2')\n", "utf-8")
    (tmp_path / "scripts" / "wsl").mkdir(parents=True)
    (tmp_path / "scripts" / "wsl" / "ros_env.sh").write_text("return 0\n", encoding="utf-8")
    a = tmp_path / "artifacts"
    want = [a / "d2/runs/normal-20260930-002844", a / "d4/batch-20260930-013010/runs/bypass-20260930-013406",
            a / "d5/batch-20260930-021530/runs/normal-20260930-021530", a / "d5/demo/runs/cancel-20260930-021343"]
    for d in want:
        (d / "rosbag").mkdir(parents=True)
        (d / "cmd_vel.txt").write_text("", encoding="utf-8")
    (a / "d0d/run-01/attempt-01/rosbag").mkdir(parents=True)          # D0 layout: neither half covers it
    (a / "d2/fake-01/abort/fake-20260930-002401").mkdir(parents=True)  # fake-node run: no cmd_vel.txt
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp"), "LANG": "C.UTF-8",
           "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(["bash", str(here / "run_bag_scans.sh")], capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    got = [line.split(" ", 1)[1] for line in p.stdout.splitlines() if line.startswith("PLAN ")]
    assert got == sorted(str(d) for d in want)
    assert "plan_heading.py: 4 run dirs" in p.stdout and "cmd_vel_scan.py: 2 rows" in p.stdout
