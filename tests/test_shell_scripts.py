"""Stub-based tests of the WSL shell scripts (tests/shell/test_*.sh, helpers in tests/shell/lib.sh).

Each bash test copies the script under test into a temporary repository skeleton and runs it with stub binaries first
on PATH and a fake /proc tree, so no ROS graph is contacted and no real process is signalled.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SHELL_TESTS = sorted((Path(__file__).parent / "shell").glob("test_*.sh"))


@pytest.mark.parametrize("script", SHELL_TESTS, ids=lambda p: p.name)
def test_shell_script(script: Path, tmp_path: Path) -> None:
    env = dict(os.environ, TMPDIR=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    run = subprocess.run(["bash", str(script)], capture_output=True, text=True, env=env, timeout=300)
    assert run.returncode == 0, f"{script.name} failed:\n{run.stdout}\n{run.stderr}"
