"""Fixed-input tests for the declared Nav2 parameter change (D5): one leaf per change, every other byte kept."""
from __future__ import annotations

import pytest
import yaml

from robosim_eval.nav2_params import apply_changes, node_and_param, write_params

VENDOR_LIKE = """controller_server:
  ros__parameters:
    use_sim_time: True
    goal_checker_plugins: ["general_goal_checker"]
    general_goal_checker:
      stateful: True
      xy_goal_tolerance: 0.25
  # DWB parameters
    FollowPath:
      plugin: "dwb_core::DWBLocalPlanner"
      max_vel_x: 0.8   # m/s
      max_vel_theta: 0.7
velocity_smoother:
  ros__parameters:
    max_velocity: [0.8, 0.0, 0.7]
    max_vel_x: 0.8
"""
PATH = "controller_server.ros__parameters.FollowPath.max_vel_x"


def test_changes_exactly_one_line_and_keeps_the_comment():
    new, applied = apply_changes(VENDOR_LIKE, {PATH: 0.4})
    old_lines, new_lines = VENDOR_LIKE.splitlines(), new.splitlines()
    assert len(old_lines) == len(new_lines)
    diff = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
    assert diff == [("      max_vel_x: 0.8   # m/s", "      max_vel_x: 0.4   # m/s")]
    assert applied == [{"path": PATH, "old": 0.8, "new": 0.4}]


def test_same_leaf_name_elsewhere_is_untouched():
    new, _ = apply_changes(VENDOR_LIKE, {PATH: 0.4})
    data = yaml.safe_load(new)
    assert data["controller_server"]["ros__parameters"]["FollowPath"]["max_vel_x"] == 0.4
    assert data["velocity_smoother"]["ros__parameters"]["max_vel_x"] == 0.8


def test_comment_line_between_keys_does_not_break_the_path():
    new, _ = apply_changes(VENDOR_LIKE, {"controller_server.ros__parameters.general_goal_checker.xy_goal_tolerance": 0.1})
    assert yaml.safe_load(new)["controller_server"]["ros__parameters"]["general_goal_checker"]["xy_goal_tolerance"] == 0.1


def test_unknown_path_is_an_error():
    with pytest.raises(ValueError, match="not found"):
        apply_changes(VENDOR_LIKE, {"controller_server.ros__parameters.FollowPath.max_vel_z": 0.4})


def test_path_to_a_mapping_is_an_error():
    with pytest.raises(ValueError, match="not a scalar"):
        apply_changes(VENDOR_LIKE, {"controller_server.ros__parameters.FollowPath": 0.4})


def test_type_change_is_an_error():
    with pytest.raises(ValueError, match="type"):
        apply_changes(VENDOR_LIKE, {PATH: "fast"})


def test_empty_change_set_is_an_error():
    with pytest.raises(ValueError, match="no change"):
        apply_changes(VENDOR_LIKE, {})


def test_node_and_param_split():
    assert node_and_param(PATH) == ("controller_server", "FollowPath.max_vel_x")
    with pytest.raises(ValueError, match="ros__parameters"):
        node_and_param("controller_server.FollowPath.max_vel_x")


def test_write_params_records_source_digest_and_changes(tmp_path):
    vendor = tmp_path / "vendor.yaml"
    vendor.write_text(VENDOR_LIKE, encoding="utf-8")
    info = write_params(vendor, tmp_path / "run", {PATH: 0.4})
    out = tmp_path / "run" / "nav2_params.yaml"
    assert info["file"] == str(out) and out.read_text(encoding="utf-8") == apply_changes(VENDOR_LIKE, {PATH: 0.4})[0]
    assert info["source"] == str(vendor) and len(info["sha256"]) == 64 and len(info["source_sha256"]) == 64
    assert info["changes"] == [{"path": PATH, "old": 0.8, "new": 0.4, "node": "controller_server",
                                "param": "FollowPath.max_vel_x"}]


# ---- review round 1: doctor_config-7/-8/-9 --------------------------------------------------------------------------

# Structure of the vendor carter_navigation_params.yaml (Isaac ROS 6.1), lines 186-226 and 228-254, shortened: literal
# dotted critic keys under FollowPath, a namespaced costmap node, trailing blanks after a mapping.
VENDOR_EXCERPT = """controller_server:
  ros__parameters:
    use_sim_time: True
  # DWB parameters
    FollowPath:
      plugin: "dwb_core::DWBLocalPlanner"
      max_vel_x: 0.8
      vx_samples: 20
      short_circuit_trajectory_evaluation: True
      critics: ["RotateToGoal", "Oscillation", "BaseObstacle", "GoalAlign", "PathAlign", "PathDist", "GoalDist"]
      BaseObstacle.scale: 0.02
      PathAlign.scale: 32.0
      PathAlign.forward_point_distance: 0.1


local_costmap:
  local_costmap:
    ros__parameters:
      use_sim_time: True
      width: 6
      inflation_layer:
        plugin: "nav2_costmap_2d::InflationLayer"
        cost_scaling_factor: 3.0
        inflation_radius: 0.8

global_costmap:
  global_costmap:
    ros__parameters:
      inflation_layer:
        inflation_radius: 1.0
"""
FOLLOW = "controller_server.ros__parameters.FollowPath."
COSTMAP = "local_costmap.local_costmap.ros__parameters.inflation_layer.inflation_radius"


def changed_lines(old: str, new: str):
    a, b = old.splitlines(), new.splitlines()
    assert len(a) == len(b)
    return [(x, y) for x, y in zip(a, b) if x != y]


def test_integer_for_a_double_parameter_is_refused():
    with pytest.raises(ValueError, match=r"0.8 \(double\), change 1 \(integer\).*write 1.0"):
        apply_changes(VENDOR_EXCERPT, {FOLLOW + "max_vel_x": 1})


def test_double_for_an_integer_parameter_is_refused():
    with pytest.raises(ValueError, match=r"20 \(integer\), change 12.5 \(double\)"):
        apply_changes(VENDOR_EXCERPT, {FOLLOW + "vx_samples": 12.5})


def test_bool_for_a_number_is_refused():
    with pytest.raises(ValueError, match="bool"):
        apply_changes(VENDOR_EXCERPT, {FOLLOW + "vx_samples": True})


def test_whole_number_double_keeps_its_decimal_point():
    new, applied = apply_changes(VENDOR_EXCERPT, {FOLLOW + "max_vel_x": 1.0})
    assert changed_lines(VENDOR_EXCERPT, new) == [("      max_vel_x: 0.8", "      max_vel_x: 1.0")]
    assert isinstance(applied[0]["new"], float)


def test_literal_dotted_parameter_name_is_addressable():
    path = FOLLOW + "PathAlign.scale"
    new, applied = apply_changes(VENDOR_EXCERPT, {path: 16.0})
    assert changed_lines(VENDOR_EXCERPT, new) == [("      PathAlign.scale: 32.0", "      PathAlign.scale: 16.0")]
    assert applied == [{"path": path, "old": 32.0, "new": 16.0}]
    assert node_and_param(path) == ("controller_server", "FollowPath.PathAlign.scale")


def test_namespaced_costmap_node_is_addressable_and_the_other_costmap_is_untouched(tmp_path):
    vendor = tmp_path / "vendor.yaml"
    vendor.write_text(VENDOR_EXCERPT, encoding="utf-8")
    info = write_params(vendor, tmp_path / "run", {COSTMAP: 0.9})
    new = (tmp_path / "run" / "nav2_params.yaml").read_text(encoding="utf-8")
    assert changed_lines(VENDOR_EXCERPT, new) == [("        inflation_radius: 0.8", "        inflation_radius: 0.9")]
    assert info["changes"] == [{"path": COSTMAP, "old": 0.8, "new": 0.9, "node": "local_costmap/local_costmap",
                                "param": "inflation_layer.inflation_radius"}]


def test_unknown_node_is_named_in_the_error():
    with pytest.raises(ValueError, match="node 'planner_server' not found"):
        apply_changes(VENDOR_EXCERPT, {"planner_server.ros__parameters.GridBased.tolerance": 0.4})


def test_unknown_parameter_is_named_with_its_node():
    with pytest.raises(ValueError, match="'FollowPath.max_vel_z' not found under controller_server.ros__parameters"):
        apply_changes(VENDOR_EXCERPT, {FOLLOW + "max_vel_z": 0.4})


def test_parameter_spelled_two_ways_is_ambiguous():
    text = VENDOR_EXCERPT.replace("      PathAlign.forward_point_distance: 0.1\n",
                                  "      PathAlign.forward_point_distance: 0.1\n      PathAlign:\n        scale: 8.0\n")
    with pytest.raises(ValueError, match="ambiguous"):
        apply_changes(text, {FOLLOW + "PathAlign.scale": 16.0})


def test_leaf_on_two_lines_is_refused():
    text = VENDOR_EXCERPT.replace("      vx_samples: 20\n", "      vx_samples: 20\n      max_vel_x: 0.8\n")
    with pytest.raises(ValueError, match="found on 2 lines"):
        apply_changes(text, {FOLLOW + "max_vel_x": 0.4})


def test_leaf_inside_a_flow_mapping_is_refused_with_the_reason():
    text = "controller_server:\n  ros__parameters:\n    FollowPath: {max_vel_x: 0.8, vx_samples: 20}\n"
    with pytest.raises(ValueError, match="line of its own"):
        apply_changes(text, {FOLLOW + "max_vel_x": 0.4})


def test_yaml_error_after_the_edit_is_a_value_error():
    text = VENDOR_EXCERPT.replace("max_vel_x: 0.8", "max_vel_x: &v 0.8").replace("vx_samples: 20", "vx_samples: *v")
    with pytest.raises(ValueError, match="not valid YAML"):   # the edit drops the anchor that vx_samples refers to
        apply_changes(text, {FOLLOW + "max_vel_x": 0.4})


def test_invalid_params_file_is_a_value_error():
    with pytest.raises(ValueError, match="not valid YAML"):
        apply_changes("controller_server: [1\n", {FOLLOW + "max_vel_x": 0.4})


def test_mis_edit_of_a_continued_scalar_is_caught_by_parsing_back():
    text = VENDOR_EXCERPT.replace('      plugin: "dwb_core::DWBLocalPlanner"\n',
                                  "      plugin: dwb_core::DWBLocal\n        Planner\n")   # a plain scalar on two lines
    follow = yaml.safe_load(text)["controller_server"]["ros__parameters"]["FollowPath"]
    assert follow["plugin"] == "dwb_core::DWBLocal Planner"
    with pytest.raises(ValueError, match="differs from the declared change"):
        apply_changes(text, {FOLLOW + "plugin": "dwb_core::Other"})


@pytest.mark.parametrize("path", [
    "/local_costmap/local_costmap.ros__parameters.inflation_layer.inflation_radius",
    "local_costmap..local_costmap.ros__parameters.x",
    "controller_server.ros__parameters.",
    "controller_server.ros__parameters.FollowPath..max_vel_x",
    "ros__parameters.max_vel_x",
])
def test_node_and_param_rejects_malformed_paths(path):
    with pytest.raises(ValueError, match="ros__parameters"):
        node_and_param(path)


def test_bad_path_writes_no_file(tmp_path):
    vendor = tmp_path / "vendor.yaml"
    vendor.write_text(VENDOR_EXCERPT, encoding="utf-8")
    with pytest.raises(ValueError):
        write_params(vendor, tmp_path / "run", {"controller_server.FollowPath.max_vel_x": 0.4})
    assert not (tmp_path / "run" / "nav2_params.yaml").exists()
