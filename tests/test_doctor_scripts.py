"""Stub tests of the doctor's WSL wrappers (no ROS, no simulator): each script must use the checkout it is in.

Every script is copied into a temporary tree next to stub environment scripts and a stub doctor, then run with bash.
A script that still names a fixed checkout would run the real doctor of that checkout against the live ROS domain, so
each test first checks the script text and fails before running anything when a fixed checkout path is in the code.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WSL = REPO / "scripts" / "wsl"

STUB_DOCTOR_PY = """import os, sys
print("stub doctor", os.path.abspath(__file__), "args", sys.argv[1:], "domain", os.environ.get("ROS_DOMAIN_ID"))
sys.exit(int(os.environ.get("STUB_RC", "0")))
"""
STUB_ROS_ENV = """echo "stub ros_env $1"
export ROS_DOMAIN_ID=43
return "${STUB_ROS_ENV_RC:-0}"
"""
STUB_DDS_ENV = """export FASTRTPS_DEFAULT_PROFILES_FILE=/nonexistent/fastdds.xml
return 0
"""
STUB_DOCTOR_SH = """#!/usr/bin/env bash
n=$(( $(cat "$STUB_COUNT" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$STUB_COUNT"
echo "call $n $0 $*" >> "$STUB_LOG"
out=""
while [[ $# -gt 0 ]]; do if [[ "$1" == --out ]]; then out="$2"; fi; shift; done
mkdir -p "$out" && echo '{}' > "$out/doctor-$n.json"
if [[ $n -eq 1 ]]; then echo "verdict: sim_not_advancing (exit 10)"; exit 10; fi
echo "verdict: healthy (exit 0)"; exit 0
"""


def assert_no_fixed_checkout(script: Path) -> None:
    code = [line for line in script.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]
    assert not [line for line in code if "/mnt/d/RoboSim-Eval" in line], f"{script.name} names a fixed checkout"


def tree(tmp_path: Path, *scripts: str) -> Path:
    """tmp/repo with the named real scripts, stub env scripts and a stub robosim_eval.doctor."""
    root = tmp_path / "repo"
    (root / "scripts" / "wsl").mkdir(parents=True)
    (root / "robosim_eval").mkdir()
    (root / "robosim_eval" / "__init__.py").write_text("", encoding="utf-8")
    (root / "robosim_eval" / "doctor.py").write_text(STUB_DOCTOR_PY, encoding="utf-8")
    (root / "scripts" / "wsl" / "ros_env.sh").write_text(STUB_ROS_ENV, encoding="utf-8")
    (root / "scripts" / "wsl" / "dds_env.sh").write_text(STUB_DDS_ENV, encoding="utf-8")
    for name in scripts:
        assert_no_fixed_checkout(WSL / name)
        shutil.copy(WSL / name, root / "scripts" / "wsl" / name)
    return root


def run(script: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    full_env = {k: v for k, v in os.environ.items() if k not in ("ROBOSIM_DOCTOR_DOMAIN", "STUB_RC", "STUB_ROS_ENV_RC")}
    full_env.update(env, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, timeout=60, env=full_env,
                          cwd=str(script.parent.parent.parent.parent))


@pytest.mark.parametrize("name", ["doctor.sh", "test_doctor_fake.sh", "doctor_watch_pause.sh"])
def test_script_derives_the_checkout_from_its_own_location(name: str):
    assert_no_fixed_checkout(WSL / name)
    assert 'dirname "${BASH_SOURCE[0]}"' in (WSL / name).read_text(encoding="utf-8")


def test_doctor_sh_runs_the_doctor_and_default_config_of_its_own_checkout(tmp_path: Path):
    root = tree(tmp_path, "doctor.sh")
    res = run(root / "scripts" / "wsl" / "doctor.sh", "--out", "x")
    assert res.returncode == 0, res.stderr
    assert f"stub doctor {root / 'robosim_eval' / 'doctor.py'}" in res.stdout
    assert f"'--config', '{root / 'configs' / 'baseline.yaml'}', '--out', 'x'" in res.stdout


def test_doctor_sh_passes_the_doctor_exit_code_and_the_test_domain(tmp_path: Path):
    root = tree(tmp_path, "doctor.sh")
    res = run(root / "scripts" / "wsl" / "doctor.sh", STUB_RC="12", ROBOSIM_DOCTOR_DOMAIN="44")
    assert res.returncode == 12 and "domain 44" in res.stdout


def test_doctor_sh_reports_a_broken_ros_environment_as_13(tmp_path: Path):
    root = tree(tmp_path, "doctor.sh")
    res = run(root / "scripts" / "wsl" / "doctor.sh", STUB_ROS_ENV_RC="1")
    assert res.returncode == 13
    assert "stub doctor" not in res.stdout and "environment" in res.stderr


def test_doctor_watch_pause_uses_the_doctor_sh_next_to_it(tmp_path: Path):
    root = tree(tmp_path, "doctor_watch_pause.sh")
    stub = root / "scripts" / "wsl" / "doctor.sh"
    stub.write_text(STUB_DOCTOR_SH, encoding="utf-8")
    out, log = tmp_path / "watch", tmp_path / "stub.log"
    res = run(root / "scripts" / "wsl" / "doctor_watch_pause.sh", str(out), "30",
              STUB_COUNT=str(tmp_path / "count"), STUB_LOG=str(log))
    assert res.returncode == 0, res.stdout + res.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2 and all(f" {stub} --window 3 --out " in c for c in calls)
    assert (out / "paused" / "doctor.txt").is_file() and (out / "resumed" / "doctor.txt").is_file()


def test_test_doctor_fake_honours_the_test_domain_and_checks_its_import():
    text = (WSL / "test_doctor_fake.sh").read_text(encoding="utf-8")
    assert 'DOMAIN="${ROBOSIM_TEST_DOMAIN:-42}"' in text
    assert "ROS_DOMAIN_ID=42" not in text and 'ROS_DOMAIN_ID="$DOMAIN"' in text
    assert "robosim_eval.doctor as d; print(d.__file__)" in text
