"""Fixed-input tests for the pure helpers behind the Isaac sim_control adapter (no ROS needed)."""
from __future__ import annotations

import math

import pytest

from robosim_eval.sim_math import (
    SPAWN_ROOT,
    Pose2D,
    angle_diff,
    check_reset,
    quat_from_yaw,
    state_code,
    state_name,
    validate_spawn_name,
    yaw_from_quat,
)

SPAWN = Pose2D(-6.0, -1.0, math.pi)


def test_yaw_quaternion_round_trip():
    for yaw in (0.0, 0.5, -1.2, math.pi - 1e-9, -math.pi + 1e-9):
        assert yaw_from_quat(*quat_from_yaw(yaw)) == pytest.approx(yaw, abs=1e-9)


def test_spawn_quaternion_from_usd_is_yaw_pi():
    # D0 USD inspection: orient (w=6.1e-17, x=0, y=0, z=1)
    assert abs(yaw_from_quat(0.0, 0.0, 1.0, 6.1e-17)) == pytest.approx(math.pi, abs=1e-9)


def test_angle_diff_wraps_across_pi():
    assert angle_diff(math.pi - 0.01, -math.pi + 0.01) == pytest.approx(-0.02, abs=1e-9)
    assert angle_diff(0.1, -0.1) == pytest.approx(0.2, abs=1e-9)


def test_reset_check_passes_at_spawn_and_at_rest():
    res = check_reset(Pose2D(-6.003, -1.001, -math.pi + 0.01), 0.001, 0.002, SPAWN)
    assert res.ok and res.position_error_m < 0.01 and abs(res.yaw_error_rad) < 0.02


def test_reset_check_fails_when_robot_is_elsewhere():
    res = check_reset(Pose2D(-2.65, -0.15, math.pi), 0.0, 0.0, SPAWN)
    assert not res.ok and any("position" in r for r in res.reasons)


def test_reset_check_fails_on_heading():
    res = check_reset(Pose2D(-6.0, -1.0, math.pi / 2), 0.0, 0.0, SPAWN)
    assert not res.ok and any("yaw" in r for r in res.reasons)


def test_reset_check_fails_when_still_moving():
    res = check_reset(Pose2D(-6.0, -1.0, math.pi), 0.3, 0.0, SPAWN)
    assert not res.ok and any("moving" in r for r in res.reasons)


def test_state_names_and_codes():
    assert state_name(1) == "playing" and state_name(2) == "paused" and state_name(0) == "stopped"
    assert state_code("playing") == 1 and state_code("paused") == 2 and state_code("stopped") == 0


def test_quitting_can_never_be_requested():
    with pytest.raises(ValueError, match="quit"):
        state_code("quitting")
    with pytest.raises(ValueError):
        state_code("no_world")


def test_spawn_names_are_confined_to_the_tool_root():
    assert validate_spawn_name(f"{SPAWN_ROOT}/box_1") == f"{SPAWN_ROOT}/box_1"
    assert validate_spawn_name("box_1") == f"{SPAWN_ROOT}/box_1"
    for bad in ("/World/Nova_Carter_ROS", "/World/RoboSimObstaclesX/a", f"{SPAWN_ROOT}/../Nova_Carter_ROS", "", "a/b"):
        with pytest.raises(ValueError):
            validate_spawn_name(bad)
