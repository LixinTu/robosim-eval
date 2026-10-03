"""Terminal Ctrl-C through scripts/wsl/run_scenario.sh (runner-2, docs-2) with stubs only, no ROS: the wrapper is copied
into a temporary tree whose ros_env.sh / dds_env.sh stubs only set variables, and a `python3` stub on PATH stands in
for the runner (exit 20 on SIGINT, like Runner.run; exit 0 after 8 s otherwise). The wrapper runs as a non-interactive
bash on a new pseudo-terminal and ^C is written to the terminal once the stub runs, as a console Ctrl-C arrives through
wsl.exe. The fake-node test (scripts/wsl/test_runner_fake.sh, case pty_ctrl_c) repeats this with the real runner."""
from __future__ import annotations

import os
import pty
import select
import shutil
import signal
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STUB_PYTHON = """#!/usr/bin/env bash
if [[ "${1:-} ${2:-}" != "-m robosim_eval.runner" ]]; then exec /usr/bin/python3 "$@"; fi
trap 'echo "stub: SIGINT" >> "$STUB_LOG"; exit 20' INT
echo "stub: started domain=${ROS_DOMAIN_ID:-unset} cwd=$PWD args=$*" >> "$STUB_LOG"
touch "$STUB_READY"
for _ in $(seq 1 80); do sleep 0.1; done
exit 0
"""


def wrapper_tree(tmp_path: Path) -> Path:
    wsl = tmp_path / "repo" / "scripts" / "wsl"
    wsl.mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "wsl" / "run_scenario.sh", wsl / "run_scenario.sh")
    (wsl / "ros_env.sh").write_text("export ROS_DOMAIN_ID=0\n", encoding="utf-8")
    (wsl / "dds_env.sh").write_text("export FASTRTPS_DEFAULT_PROFILES_FILE=/dev/null\n", encoding="utf-8")
    stub = tmp_path / "bin" / "python3"
    stub.parent.mkdir()
    stub.write_text(STUB_PYTHON, encoding="utf-8")
    stub.chmod(0o755)
    return wsl / "run_scenario.sh"


def run_on_a_terminal(script: Path, env: dict, ready: Path, ctrl_c: bool, deadline: float = 20.0):
    """(exit code, seconds from ^C to exit or None) of `bash script fake --no-sim` on a new pseudo-terminal."""
    pid, fd = pty.fork()
    if pid == 0:  # child: session leader with the pty as its controlling terminal, as under wsl.exe
        os.execvpe("bash", ["bash", str(script), "fake", "--no-sim"], env)
    t0, sent = time.monotonic(), None
    try:
        while True:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    os.read(fd, 4096)
                except OSError:
                    pass
            if ctrl_c and sent is None and ready.exists():
                time.sleep(0.3)
                os.write(fd, b"\x03")
                sent = time.monotonic()
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                return os.waitstatus_to_exitcode(status), (time.monotonic() - sent) if sent else None
            if time.monotonic() - t0 > deadline:
                os.killpg(pid, signal.SIGKILL)   # only the processes this test started (the pty session)
                os.waitpid(pid, 0)
                pytest.fail("the wrapper did not end within the deadline")
    finally:
        os.close(fd)


def env_for(tmp_path: Path, **extra) -> dict:
    env = dict(os.environ, PATH=f"{tmp_path / 'bin'}:{os.environ.get('PATH', '')}", STUB_LOG=str(tmp_path / "stub.log"),
               STUB_READY=str(tmp_path / "ready"))
    env.pop("ROBOSIM_RUN_DOMAIN", None)
    env.update(extra)
    return env


def test_a_terminal_ctrl_c_reaches_the_runner(tmp_path):
    script = wrapper_tree(tmp_path)
    rc, after = run_on_a_terminal(script, env_for(tmp_path, ROBOSIM_RUN_DOMAIN="42"), tmp_path / "ready", ctrl_c=True)
    log = (tmp_path / "stub.log").read_text(encoding="utf-8")
    assert "stub: SIGINT" in log and rc == 20 and after is not None and after < 3.0, (rc, after, log)
    assert "domain=42" in log and f"cwd={tmp_path / 'repo'}" in log      # ROBOSIM_RUN_DOMAIN; its own checkout (C6)
    assert "args=-m robosim_eval.runner --scenario fake --no-sim" in log


def test_without_ctrl_c_the_run_ends_normally_on_the_configured_domain(tmp_path):
    script = wrapper_tree(tmp_path)
    rc, _ = run_on_a_terminal(script, env_for(tmp_path), tmp_path / "ready", ctrl_c=False)
    log = (tmp_path / "stub.log").read_text(encoding="utf-8")
    assert rc == 0 and "SIGINT" not in log and "domain=0" in log
