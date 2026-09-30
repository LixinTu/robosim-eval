"""Fixed-input tests for loading configs/baseline.yaml into frozen dataclasses."""
from __future__ import annotations

from pathlib import Path

import pytest

from robosim_eval.config import load_config

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "configs" / "baseline.yaml"


def test_baseline_config_has_the_topics_measured_in_d0():
    cfg = load_config(BASELINE)
    assert cfg.topics["clock"].name == "/clock"
    assert cfg.topics["odom"].name == "/chassis/odom"
    assert cfg.topics["tf"].child == "base_link" and cfg.topics["tf"].parent == "odom"
    assert cfg.topics["lidar"].msg_type == "sensor_msgs/msg/PointCloud2"
    assert cfg.env.rmw == "rmw_fastrtps_cpp" and cfg.env.domain_id == "0"


def test_baseline_doctor_thresholds_are_bounded_and_below_measured_rates():
    d = load_config(BASELINE).doctor
    assert 0 < d.discovery_timeout_s <= 10 and 0 < d.window_s <= 10
    assert d.thresholds.clock_stall_s >= 2.0
    # measured minimums on this machine: ~19 Hz for odom/tf while navigating, 2.4 Hz for the point cloud
    assert d.thresholds.streams["odom"].min_rate_hz < 19
    assert d.thresholds.streams["lidar"].min_rate_hz < 2.4
    assert set(d.thresholds.streams) == {"odom", "tf", "lidar"}


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text(text, encoding="utf-8")
    return p


GOOD = """
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


def test_minimal_valid_config_loads(tmp_path: Path):
    cfg = load_config(write(tmp_path, GOOD))
    assert cfg.doctor.thresholds.streams["odom"].min_rate_hz == 8.0


def test_numeric_domain_id_is_read_as_text(tmp_path: Path):
    cfg = load_config(write(tmp_path, GOOD.replace('domain_id: "0"', "domain_id: 42")))
    assert cfg.env.domain_id == "42"


def test_non_positive_window_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="window_s"):
        load_config(write(tmp_path, GOOD.replace("window_s: 5", "window_s: 0")))


def test_stream_without_topic_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="lidar"):
        load_config(write(tmp_path, GOOD.replace("odom: {min_rate_hz", "lidar: {min_rate_hz")))


def test_missing_clock_topic_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="clock"):
        load_config(write(tmp_path, GOOD.replace("  clock: {name: /clock, type: rosgraph_msgs/msg/Clock}\n", "")))


def test_missing_file_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_baseline_sim_section_has_world_robot_and_spawn():
    import math
    sim = load_config(BASELINE).sim
    assert sim is not None
    assert sim.world_uri.endswith("/Isaac/Samples/ROS2/Scenario/carter_warehouse_navigation.usd")
    assert sim.robot_entity == "/World/Nova_Carter_ROS/chassis_link"
    assert (sim.spawn.x, sim.spawn.y) == (-6.0, -1.0) and sim.spawn.yaw == pytest.approx(math.pi)
    assert 0 < sim.reset_position_m <= 0.1 and 0 < sim.reset_yaw_rad <= 0.1


def test_config_without_sim_section_has_no_sim(tmp_path: Path):
    assert load_config(write(tmp_path, GOOD)).sim is None


def test_baseline_run_section_has_the_a5_fields():
    run = load_config(BASELINE).run
    assert run is not None and run.frame == "map" and run.units == {"length": "m", "angle": "rad"}
    assert run.position_tolerance_m == 0.5 and run.heading_assessed is False
    assert (run.stop_linear_mps, run.stop_angular_radps, run.stop_hold_sim_s) == (0.05, 0.1, 1.0)
    lim = run.limits
    assert (lim.accept_wall_s, lim.nav_sim_s, lim.nav_wall_s, lim.cancel_wall_s, lim.stop_wall_s) == (10, 120, 300, 10, 10)
    assert lim.ready_wall_s > 0 and run.dropout_wall_s == 2.0 and run.contact_filter


def test_baseline_scenarios_match_the_d3_d4_plan():
    sc = load_config(BASELINE).scenarios
    assert set(sc) == {"normal", "bypass", "unreachable"}
    assert (sc["normal"].goal.x, sc["normal"].goal.y) == (0.0, -1.0) and not sc["normal"].obstacles
    assert [(o.name, o.x, o.y) for o in sc["bypass"].obstacles] == [("box_1", -3.0, -1.3)]
    assert (sc["unreachable"].goal.x, sc["unreachable"].goal.y) == (-10.05, -1.0)


def test_scenario_obstacle_outside_the_tool_root_is_rejected(tmp_path: Path):
    text = GOOD + """
scenarios:
  s1:
    goal: {x: 0.0, y: 0.0, yaw: 0.0}
    obstacles: [{name: /World/Nova_Carter_ROS, x: 0.0, y: 0.0}]
"""
    with pytest.raises(ValueError, match="RoboSimObstacles"):
        load_config(write(tmp_path, text))
