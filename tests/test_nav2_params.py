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
