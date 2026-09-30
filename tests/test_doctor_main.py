"""Fixed-input tests of the doctor's command line (robosim_eval.doctor.main): exit codes without any ROS graph.

2 = usage or config error (one-line message), 13 = environment error, including every environment problem that stops
ROS 2 from starting; never a traceback with exit 1. observe() is replaced wherever the ROS graph would be needed.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import List

import pytest

from robosim_eval import doctor
from robosim_eval.doctor_checks import EXIT_ENV, EXIT_HEALTHY, EnvFacts, Observation, StreamObservation

CONFIG = """
env: {rmw: rmw_fastrtps_cpp, domain_id: "0", ros_distro: jazzy, require_dds_profile: true}
topics:
  clock: {name: /clock, type: rosgraph_msgs/msg/Clock}
  odom: {name: /chassis/odom, type: nav_msgs/msg/Odometry}
doctor:
  discovery_timeout_s: 5
  window_s: 5
  clock_stall_s: 2
  min_sim_progress_s: 0.2
  streams:
    odom: {min_rate_hz: 8, max_age_s: 2}
"""


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A valid config and an environment that matches it, with an ament index that lists Fast DDS."""
    profile = tmp_path / "fastdds.xml"
    profile.write_text("<profiles/>", encoding="utf-8")
    for key, value in (("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"), ("ROS_DOMAIN_ID", "0"), ("ROS_DISTRO", "jazzy"),
                       ("FASTRTPS_DEFAULT_PROFILES_FILE", str(profile))):
        monkeypatch.setenv(key, value)
    fake_index = types.ModuleType("ament_index_python")
    fake_index.get_resources = lambda kind: {"rmw_fastrtps_cpp": "/opt/ros/jazzy"} if kind == "rmw_typesupport" else {}
    monkeypatch.setitem(sys.modules, "ament_index_python", fake_index)
    path = tmp_path / "cfg.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


def healthy(window_s: float) -> Observation:
    clock = tuple((100.0 + i * 0.05, 500.0 + i * 0.016) for i in range(int(window_s / 0.05)))
    odom = StreamObservation(present=True, msg_types=("nav_msgs/msg/Odometry",),
                             samples=tuple((t, s) for t, s in clock))
    env = doctor.current_env()
    return Observation(window_start=100.0, window_end=100.0 + window_s, clock_present=True,
                       clock_types=("rosgraph_msgs/msg/Clock",), clock=clock, streams={"odom": odom}, env=env)


def no_ros(*_args, **_kwargs):
    raise AssertionError("observe() must not run: nothing may touch ROS here")


def one_line_errors(caplog: pytest.LogCaptureFixture) -> List[str]:
    msgs = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert msgs and all("\n" not in m for m in msgs)
    return msgs


@pytest.mark.parametrize("text", ["env: [1\n", "env: {rmw: x}\nextra: 1\n", "topics:\n  clock:\n"])
def test_malformed_config_exits_2_with_one_line(tmp_path: Path, cfg: Path, text: str, monkeypatch, caplog):
    bad = tmp_path / "bad.yaml"
    bad.write_text(text, encoding="utf-8")
    monkeypatch.setattr(doctor, "observe", no_ros)
    assert doctor.main(["--config", str(bad)]) == 2
    assert "config error" in one_line_errors(caplog)[0]


@pytest.mark.parametrize("window", ["0", "-5", "nan", "inf", "0.6", "100"])
def test_window_outside_its_bounds_exits_2(cfg: Path, window: str, monkeypatch, caplog):
    monkeypatch.setattr(doctor, "observe", no_ros)
    assert doctor.main(["--config", str(cfg), "--window", window]) == 2
    assert "--window" in one_line_errors(caplog)[0]


def test_window_inside_its_bounds_is_observed(cfg: Path, monkeypatch):
    seen = []
    monkeypatch.setattr(doctor, "observe", lambda c, w, d: seen.append((w, d)) or healthy(w))
    assert doctor.main(["--config", str(cfg), "--window", "3"]) == EXIT_HEALTHY
    assert seen == [(3.0, 5.0)]


def test_environment_mismatch_exits_13_before_touching_ros(tmp_path: Path, cfg: Path, monkeypatch):
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_zenoh_cpp")
    monkeypatch.setattr(doctor, "observe", no_ros)
    assert doctor.main(["--config", str(cfg), "--out", str(tmp_path / "out")]) == EXIT_ENV
    report = json.loads(next((tmp_path / "out").glob("doctor-*.json")).read_text(encoding="utf-8"))["report"]
    assert report["verdict"] == "env_or_interface_error" and report["observed"] is False
    assert any("rmw_zenoh_cpp" in r for r in report["reasons"])


def test_rmw_that_is_not_installed_exits_13_before_importing_rclpy(cfg: Path, monkeypatch, capsys):
    # rcl ends the whole process with status 1 when it cannot load the RMW library, so this is checked beforehand
    sys.modules["ament_index_python"].get_resources = lambda kind: {"rmw_cyclonedds_cpp": "/opt/ros/jazzy"}
    monkeypatch.setattr(doctor, "observe", no_ros)
    assert doctor.main(["--config", str(cfg)]) == EXIT_ENV
    assert "rmw_fastrtps_cpp" in capsys.readouterr().out


def test_ros_that_fails_to_start_exits_13(cfg: Path, monkeypatch, capsys):
    def start_fails(*_args):
        raise doctor.RosStartError("rclpy.init failed: ROS_DOMAIN_ID is not an integral number")
    monkeypatch.setattr(doctor, "observe", start_fails)
    assert doctor.main(["--config", str(cfg)]) == EXIT_ENV
    assert "ROS_DOMAIN_ID is not an integral number" in capsys.readouterr().out


def test_missing_ros_python_exits_13(cfg: Path, monkeypatch):
    def no_rclpy(*_args):
        raise ImportError("No module named 'rclpy'")
    monkeypatch.setattr(doctor, "observe", no_rclpy)
    assert doctor.main(["--config", str(cfg)]) == EXIT_ENV


def test_unsupported_topic_type_is_a_config_error(cfg: Path, monkeypatch):
    def unsupported(*_args):
        raise ValueError("topics.odom: unsupported message type x/msg/Y")
    monkeypatch.setattr(doctor, "observe", unsupported)
    assert doctor.main(["--config", str(cfg)]) == 2


def test_rmw_check_needs_no_ros_environment(monkeypatch):
    monkeypatch.setitem(sys.modules, "ament_index_python", None)   # import fails: rclpy's own import reports it (13)
    assert doctor.rmw_problems("rmw_fastrtps_cpp") == []
    assert doctor.rmw_problems(None) == []


def test_env_facts_default_the_domain_like_ros(monkeypatch):
    monkeypatch.delenv("ROS_DOMAIN_ID", raising=False)
    assert doctor.current_env().domain_id == "0"
    assert isinstance(doctor.current_env(), EnvFacts)
