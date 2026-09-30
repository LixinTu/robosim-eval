"""Fixed-input tests for the pure helpers behind the Isaac sim_control adapter (no ROS needed)."""
from __future__ import annotations

import math
import sys
import types
from types import SimpleNamespace as NS

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


@pytest.mark.parametrize("pose, v, w", [
    (Pose2D(math.nan, math.nan, math.nan), 0.0, 0.0),                    # physics blow-up: every field NaN
    (Pose2D(math.nan, -1.0, math.pi), 0.0, 0.0),                         # one coordinate NaN, the rest at the spawn
    (Pose2D(-6.0, -1.0, math.nan), 0.0, 0.0),                            # heading NaN (e.g. from a NaN quaternion)
    (Pose2D(-6.0, -1.0, math.pi), math.nan, 0.0),                        # pose at the spawn, speeds NaN
    (Pose2D(-6.0, -1.0, math.pi), 0.0, math.nan),
    (Pose2D(-6.0, math.inf, math.pi), 0.0, 0.0),
    (Pose2D(-6.0, -1.0, math.pi), 0.0, -math.inf),
])
def test_reset_check_fails_closed_on_non_finite_ground_truth(pose, v, w):
    # every comparison with NaN is False, so without an explicit check a NaN ground truth would pass the reset check
    res = check_reset(pose, v, w, SPAWN)
    assert not res.ok
    assert any("not finite" in r for r in res.reasons)


def _entity_state(frame_id: str) -> NS:
    """Duck-typed simulation_interfaces/EntityState as Isaac's GetEntityState fills it (D5 normal run, at stop)."""
    return NS(header=NS(frame_id=frame_id),
              pose=NS(position=NS(x=0.032, y=-1.037, z=0.1), orientation=NS(x=0.0, y=0.0, z=0.0, w=1.0)),
              twist=NS(linear=NS(x=0.3, y=0.4, z=0.0), angular=NS(x=0.0, y=0.0, z=-0.2)))


def _adapter_returning(monkeypatch, state: NS):
    """SimAdapter whose service call returns a fixed GetEntityState response (no ROS: the srv module is faked)."""
    srv = types.ModuleType("simulation_interfaces.srv")
    srv.GetEntityState = NS(Request=lambda: NS(entity=""))
    pkg = types.ModuleType("simulation_interfaces")
    pkg.srv = srv
    monkeypatch.setitem(sys.modules, "simulation_interfaces", pkg)
    monkeypatch.setitem(sys.modules, "simulation_interfaces.srv", srv)
    from robosim_eval.sim_adapter import RESULT_OK, SimAdapter
    sim = SimAdapter(node=None)
    monkeypatch.setattr(sim, "_call", lambda _cls, _name, _req, timeout=None: NS(
        result=NS(result=RESULT_OK, error_message=""), state=state))
    return sim


def test_ground_truth_is_labelled_world_not_the_robot_name(monkeypatch):
    # Isaac sets header.frame_id to the prim name ("nova_carter") although the pose comes from get_world_poses; the
    # message definition reads frame_id as the frame of the pose, so the record must say world and keep Isaac's value
    rec = _adapter_returning(monkeypatch, _entity_state("nova_carter")).entity_state("/World/Nova_Carter_ROS/chassis_link")
    assert rec["frame"] == "world"
    assert rec["isaac_frame_id"] == "nova_carter"
    assert "ground truth" in rec["source"] and "world" in rec["source"]
    # the keys older records already carry keep their meaning
    assert rec["entity"] == "/World/Nova_Carter_ROS/chassis_link" and isinstance(rec["received_wall"], float)
    assert (rec["x"], rec["y"], rec["z"]) == (0.032, -1.037, 0.1)
    assert rec["yaw"] == pytest.approx(0.0) and rec["linear_speed"] == pytest.approx(0.5)
    assert rec["angular_speed"] == pytest.approx(0.2)


def test_ground_truth_frame_is_world_when_isaac_leaves_it_empty(monkeypatch):
    # EntityState.msg: "Empty frame defaults to world"
    rec = _adapter_returning(monkeypatch, _entity_state("")).entity_state("/World/x")
    assert rec["frame"] == "world" and rec["isaac_frame_id"] == ""
