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
    assert {"normal", "bypass", "unreachable"} <= set(sc)   # the three D4 batch scenarios (D3 adds fault-injection ones)
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


def test_baseline_d3_contact_policy_and_stream_classes():
    run = load_config(BASELINE).run
    assert run.contact_robot_root == "/World/Nova_Carter_ROS"
    assert "/World/warehouse_with_forklifts/GroundPlane/" in run.contact_ignore_prefixes
    assert set(run.required_streams) == {"clock", "odom", "tf_odom_base"}
    assert set(run.informational_streams) == {"tf_map_odom"}


def test_baseline_d3_scenarios_have_expectations_and_injections():
    sc = load_config(BASELINE).scenarios
    assert sc["normal"].expect_outcome == "reached" and not sc["normal"].preset_unreachable
    assert sc["unreachable"].expect_outcome == "unreachable" and sc["unreachable"].preset_unreachable
    assert sc["unreachable"].evidence
    assert sc["cancel"].expect_outcome == "canceled" and sc["cancel"].inject.get("cancel_after_sim_s") > 0
    assert sc["dropout"].inject.get("pause_after_sim_s") > 0 and sc["dropout"].inject.get("pause_wall_s") > 2
    assert sc["timeout"].expect_outcome == "timeout" and sc["timeout"].timeouts.get("nav_sim_s") < 120
    assert sc["collision"].obstacles[0].asset == "low_box"


def test_unknown_injection_key_is_rejected(tmp_path: Path):
    text = GOOD + """
scenarios:
  s1:
    goal: {x: 0.0, y: 0.0, yaw: 0.0}
    inject: {explode_after_s: 3}
"""
    with pytest.raises(ValueError, match="inject"):
        load_config(write(tmp_path, text))


def test_scenario_nav2_param_change_is_read_as_a_mapping(tmp_path: Path):
    text = GOOD + """
scenarios:
  s1:
    goal: {x: 0.0, y: 0.0, yaw: 0.0}
    nav2_params: {controller_server.ros__parameters.FollowPath.max_vel_x: 0.4}
"""
    sc = load_config(write(tmp_path, text)).scenarios["s1"]
    assert dict(sc.nav2_params) == {"controller_server.ros__parameters.FollowPath.max_vel_x": 0.4}


def test_scenario_nav2_param_change_must_be_scalar(tmp_path: Path):
    text = GOOD + """
scenarios:
  s1:
    goal: {x: 0.0, y: 0.0, yaw: 0.0}
    nav2_params: {controller_server.ros__parameters.FollowPath: {max_vel_x: 0.4}}
"""
    with pytest.raises(ValueError, match="nav2_params"):
        load_config(write(tmp_path, text))


def test_baseline_d5_slow_scenario_differs_from_normal_only_by_the_declared_change():
    sc = load_config(BASELINE).scenarios
    slow, normal = sc["normal_slow"], sc["normal"]
    assert dict(slow.nav2_params) == {"controller_server.ros__parameters.FollowPath.max_vel_x": 0.4}
    assert not normal.nav2_params
    assert (slow.goal, slow.obstacles, slow.expect_outcome, dict(slow.inject)) == \
        (normal.goal, normal.obstacles, normal.expect_outcome, dict(normal.inject))


# ---- strict validation (review round 1: doctor_config-3/-4/-6/-10, simctl-6; contracts C2 and C3) -------------------

BASELINE_TEXT = BASELINE.read_text(encoding="utf-8")


def variant(tmp_path: Path, old: str, new: str, base: str = BASELINE_TEXT) -> Path:
    """The baseline (or `base`) with exactly one occurrence of `old` replaced; fails loudly if `old` is not there."""
    assert base.count(old) == 1, f"test setup: {old!r} occurs {base.count(old)} times"
    return write(tmp_path, base.replace(old, new))


def test_repository_configs_still_load():
    for rel in ("configs/baseline.yaml", "tests/ros_fake/doctor_fake.yaml", "tests/ros_fake/runner_fake.yaml"):
        load_config(REPO / rel)


@pytest.mark.parametrize("old,new,key", [
    ("clock_stall_s: 2", "clock_stall_s: .nan", "clock_stall_s"),
    ("clock_stall_s: 2", "clock_stall_s: .inf", "clock_stall_s"),
    ("clock_stall_s: 2", "clock_stall_s: 'nan'", "clock_stall_s"),
    ("clock_stall_s: 2", "clock_stall_s: '2'", "clock_stall_s"),
    ("clock_stall_s: 2", "clock_stall_s: true", "clock_stall_s"),
    ("min_rate_hz: 8", "min_rate_hz: .nan", "min_rate_hz"),
    ("max_age_s: 2}", "max_age_s: -.inf}", "max_age_s"),
])
def test_thresholds_must_be_finite_positive_numbers(tmp_path: Path, old: str, new: str, key: str):
    with pytest.raises(ValueError, match=key):
        load_config(variant(tmp_path, old, new, GOOD))


@pytest.mark.parametrize("old,new,key", [
    ("position_tolerance_m: 0.5", "position_tolerance_m: .nan", "position_tolerance_m"),
    ("dropout_wall_s: 2.0", "dropout_wall_s: 'nan'", "dropout_wall_s"),
    ("nav_wall_s: 300", "nav_wall_s: .nan", "nav_wall_s"),
    ("reset_check: {position_m: 0.05", "reset_check: {position_m: .nan", "position_m"),
    ("normal:\n    goal: {x: 0.0", "normal:\n    goal: {x: .nan", "goal.x"),
    ("spawn: {x: -6.0", "spawn: {x: .inf", "spawn.x"),
    ("name: box_1, x: -3.0", "name: box_1, x: .nan", "obstacles"),
    ("inject: {cancel_after_sim_s: 5.0}", "inject: {cancel_after_sim_s: .inf}", "cancel_after_sim_s"),
    ("FollowPath.max_vel_x: 0.4}", "FollowPath.max_vel_x: .nan}", "nav2_params"),
])
def test_non_finite_numbers_anywhere_are_rejected(tmp_path: Path, old: str, new: str, key: str):
    with pytest.raises(ValueError, match=key):
        load_config(variant(tmp_path, old, new))


@pytest.mark.parametrize("old,new,key", [
    ("obstacles: [{name: box_1", "obstacle: [{name: box_1", "obstacle"),                  # bypass would run empty
    ("expect_outcome: unreachable", "expected_outcome: unreachable", "expected_outcome"),
    ("  contact:\n    robot_root", "  contact:\n    root", "root"),
    ("    ignore_prefixes:", "    ignore_prefix:", "ignore_prefix"),
    ("scenarios:\n  normal:", "scenario:\n  normal:", "scenario"),
    ("  window_s: 5.0", "  window: 5.0", "window"),
    ("clock: {name: /clock, type:", "clock: {name: /clock, typ:", "typ"),
    ("reset_check: {position_m: 0.05,", "reset_check: {position: 0.05,", "position"),
    ("stop_still: {linear_mps: 0.05,", "stop_still: {linear: 0.05,", "linear"),
    ("goal: {x: 0.0, y: -1.0, yaw: 0.0}\n    obstacles: [{name: low_box",
     "goal: {x: 0.0, y: -1.0, yaw: 0.0, z: 1.0}\n    obstacles: [{name: low_box", "z"),
    ("[{name: low_box, x: -3.0,", "[{name: low_box, size: 1, x: -3.0,", "size"),
])
def test_unknown_keys_are_rejected(tmp_path: Path, old: str, new: str, key: str):
    with pytest.raises(ValueError, match=f"unknown key.*{key}"):
        load_config(variant(tmp_path, old, new))


def test_duplicate_yaml_keys_are_rejected(tmp_path: Path):
    text = BASELINE_TEXT + "  normal:\n    goal: {x: 5.0, y: 5.0, yaw: 0.0}\n"   # a second 'normal' scenario
    with pytest.raises(ValueError, match="duplicate key 'normal'"):
        load_config(write(tmp_path, text))
    with pytest.raises(ValueError, match="duplicate key 'window_s'"):
        load_config(variant(tmp_path, "  window_s: 5\n", "  window_s: 5\n  window_s: 3\n", GOOD))


def test_unknown_obstacle_asset_is_rejected_instead_of_falling_back(tmp_path: Path):
    with pytest.raises(ValueError, match="asset 'low-box'.*obstacle_assets"):
        load_config(variant(tmp_path, "asset: low_box}", "asset: low-box}"))


def test_obstacle_without_asset_needs_a_default_asset_or_obstacle_usd(tmp_path: Path):
    no_asset = "scenarios:\n  s1:\n    goal: {x: 0.0, y: 0.0, yaw: 0.0}\n    obstacles: [{name: b1, x: 1.0, y: 0.0}]\n"
    with pytest.raises(ValueError, match="obstacles.*asset"):
        load_config(write(tmp_path, GOOD + no_asset))   # no sim section: nothing to spawn it from
    sim = ("sim:\n  world_uri: w.usd\n  robot_entity: /World/r\n  spawn: {x: 0.0, y: 0.0, yaw: 0.0}\n"
           "  obstacle_usd: D:/box.usda\n")
    sc = load_config(write(tmp_path, GOOD + sim + no_asset)).scenarios["s1"]   # obstacle_usd is the documented default
    assert sc.obstacles[0].asset == "box_1m"


def test_duplicate_obstacle_names_are_rejected(tmp_path: Path):
    twice = "obstacles: [{name: box_1, x: -3.0, y: -1.3, asset: box_1m}, {name: box_1, x: -2.0, y: -1.3}]"
    with pytest.raises(ValueError, match="duplicate obstacle name 'box_1'"):
        load_config(variant(tmp_path, "obstacles: [{name: box_1, x: -3.0, y: -1.3, yaw: 0.0, asset: box_1m}]", twice))


@pytest.mark.parametrize("old,new,key", [
    ("required: [clock, odom, tf_odom_base]", "required: []", "required"),
    ("required: [clock, odom, tf_odom_base]", "required: [clock, odom, tf_odombase]", "tf_odombase"),
    ("informational: [tf_map_odom]", "informational: tf_map_odom", "informational"),
])
def test_stream_classes_must_name_known_streams(tmp_path: Path, old: str, new: str, key: str):
    with pytest.raises(ValueError, match=key):
        load_config(variant(tmp_path, old, new))


@pytest.mark.parametrize("old,new,key", [
    ("heading_assessed: false", "heading_assessed: 'false'", "heading_assessed"),
    ("require_dds_profile: true", "require_dds_profile: 'yes'", "require_dds_profile"),
    ("preset_unreachable: true", "preset_unreachable: 1", "preset_unreachable"),
    ("rmw: rmw_fastrtps_cpp", "rmw:", "rmw"),
    ('domain_id: "0"', 'domain_id: "zero"', "domain_id"),
    ('domain_id: "0"', "domain_id: 300", "domain_id"),
    ('contact_filter: "ignore contacts', 'contact_filter: 5   # "ignore contacts', "contact_filter"),
])
def test_flags_and_texts_must_have_their_type(tmp_path: Path, old: str, new: str, key: str):
    with pytest.raises(ValueError, match=key):
        load_config(variant(tmp_path, old, new))


def test_tf_topic_needs_both_parent_and_child(tmp_path: Path):
    with pytest.raises(ValueError, match="topics.tf"):
        load_config(variant(tmp_path, "parent: odom, child: base_link}", "child: base_link}"))


TOPICS_BLOCK = ("topics:\n  clock: {name: /clock, type: rosgraph_msgs/msg/Clock}\n"
                "  odom: {name: /chassis/odom, type: nav_msgs/msg/Odometry}\n")


@pytest.mark.parametrize("text", [
    GOOD.replace("window_s: 5", "window_s: [5"),                               # YAML syntax error
    GOOD + "scenarios:\n  s1:\n    goal: {x: 0.0, y: 0.0, yaw: }\n",         # null goal yaw
    GOOD.replace("odom: {min_rate_hz: 8, max_age_s: 2}", "odom:"),            # stream entry with no values
    GOOD.replace(TOPICS_BLOCK, "topics: [clock, odom]\n"),                     # non-mapping topics
    "- env\n- topics\n",                                                       # top level is not a mapping
    GOOD + "run: 5\n",
    GOOD + "scenarios:\n  s1: [goal]\n",
    GOOD + "scenarios:\n  s1:\n    goal: {x: 0.0, y: 0.0, yaw: 0.0}\n    obstacles: {name: b}\n",
    GOOD + "---\nenv: {}\n",                                                     # two YAML documents
])
def test_malformed_config_is_a_one_line_value_error(tmp_path: Path, text: str):
    assert text != GOOD and TOPICS_BLOCK in GOOD
    with pytest.raises(ValueError) as info:
        load_config(write(tmp_path, text))
    assert "\n" not in str(info.value)


def _mapping_paths(node, prefix=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield prefix + (k,)
            yield from _mapping_paths(v, prefix + (k,))


def test_any_wrongly_typed_value_in_the_baseline_is_a_value_error_not_a_crash(monkeypatch: pytest.MonkeyPatch):
    import copy

    import yaml

    import robosim_eval.config as config_module
    raw = yaml.safe_load(BASELINE_TEXT)
    paths = list(_mapping_paths(raw))
    assert len(paths) > 100
    for path in paths:
        for bad in (None, [], "x", 1, {"k": 1}):
            data = copy.deepcopy(raw)
            parent = data
            for k in path[:-1]:
                parent = parent[k]
            parent[path[-1]] = bad
            monkeypatch.setattr(config_module, "_parse", lambda _path, data=data: data)   # skip YAML: types only
            try:
                load_config(BASELINE)
            except ValueError:
                pass   # rejected with a message: fine; anything else (TypeError, AttributeError) fails the test


def test_baseline_fault_injection_scenarios_declare_their_real_expectation():
    sc = load_config(BASELINE).scenarios
    assert sc["collision"].expect_safety == "fail" and sc["collision"].expect_data is None
    assert sc["dropout"].expect_data == "incomplete" and sc["dropout"].expect_safety is None
    for name in ("normal", "normal_slow", "bypass", "unreachable", "cancel", "timeout"):
        assert (sc[name].expect_safety, sc[name].expect_data) == (None, None)


@pytest.mark.parametrize("line,key", [("expect_safety: safe", "expect_safety"),
                                      ("expect_data: partial", "expect_data")])
def test_expectation_fields_only_take_a5_values(tmp_path: Path, line: str, key: str):
    text = GOOD + f"scenarios:\n  s1:\n    goal: {{x: 0.0, y: 0.0, yaw: 0.0}}\n    {line}\n"
    with pytest.raises(ValueError, match=key):
        load_config(write(tmp_path, text))
    good = GOOD + ("scenarios:\n  s1:\n    goal: {x: 0.0, y: 0.0, yaw: 0.0}\n"
                   "    expect_safety: fail\n    expect_data: incomplete\n")
    sc = load_config(write(tmp_path, good)).scenarios["s1"]
    assert (sc.expect_safety, sc.expect_data) == ("fail", "incomplete")


@pytest.mark.parametrize("window,ok", [("0.5", False), ("1.9", False), ("2", True), ("50", True), ("51", False)])
def test_window_must_cover_the_clock_stall_and_fit_the_doctor_cap(tmp_path: Path, window: str, ok: bool):
    p = variant(tmp_path, "window_s: 5", f"window_s: {window}", GOOD)
    if ok:
        assert load_config(p).doctor.window_s == float(window)
    else:
        with pytest.raises(ValueError, match="window_s"):
            load_config(p)


@pytest.mark.parametrize("key", [
    "controller_server.FollowPath.max_vel_x",                  # no ros__parameters level
    "ros__parameters.max_vel_x",                               # no node
    "controller_server.ros__parameters.",                      # no parameter name
    "/local_costmap/local_costmap.ros__parameters.inflation_layer.inflation_radius",   # not dotted node tokens
    "controller_server.ros__parameters.FollowPath..max_vel_x",
])
def test_nav2_param_paths_are_checked_at_load(tmp_path: Path, key: str):
    text = GOOD + f"scenarios:\n  s1:\n    goal: {{x: 0.0, y: 0.0, yaw: 0.0}}\n    nav2_params: {{'{key}': 0.4}}\n"
    with pytest.raises(ValueError, match="nav2_params"):
        load_config(write(tmp_path, text))


def test_namespaced_nav2_node_and_literal_dotted_parameter_are_accepted(tmp_path: Path):
    text = GOOD + ("scenarios:\n  s1:\n    goal: {x: 0.0, y: 0.0, yaw: 0.0}\n    nav2_params:\n"
                   "      local_costmap.local_costmap.ros__parameters.inflation_layer.inflation_radius: 0.9\n"
                   "      controller_server.ros__parameters.FollowPath.PathAlign.scale: 16.0\n")
    sc = load_config(write(tmp_path, text)).scenarios["s1"]
    assert len(sc.nav2_params) == 2
