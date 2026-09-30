"""Pure helpers for the Isaac sim_control adapter: 2D pose math, reset verification and safety guards.

No ROS imports, so the rules are testable with fixed inputs (tests/test_sim_math.py).
Guards: STATE_QUITTING (it closes Isaac) and the non-controllable states can never be requested, and entities may only
be spawned or deleted under SPAWN_ROOT, so the tool can never delete the robot or the warehouse.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

__all__ = ["SPAWN_ROOT", "Pose2D", "ResetCheck", "yaw_from_quat", "quat_from_yaw", "angle_diff", "check_reset",
           "state_name", "state_code", "validate_spawn_name"]

SPAWN_ROOT = "/World/RoboSimObstacles"
_STATE_NAMES = {0: "stopped", 1: "playing", 2: "paused", 3: "quitting", 4: "no_world", 5: "loading_world"}
_REQUESTABLE = {"stopped": 0, "playing": 1, "paused": 2}


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class ResetCheck:
    ok: bool
    position_error_m: float
    yaw_error_rad: float
    linear_speed: float
    angular_speed: float
    reasons: Tuple[str, ...]


def yaw_from_quat(qx: float, qy: float, qz: float, qw: float) -> float:
    """Yaw (rotation about z) of a quaternion, in (-pi, pi]."""
    return math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))


def quat_from_yaw(yaw: float) -> Tuple[float, float, float, float]:
    """(x, y, z, w) of a pure rotation about z."""
    return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)


def angle_diff(a: float, b: float) -> float:
    """a - b wrapped to (-pi, pi]."""
    d = (a - b) % (2.0 * math.pi)
    return d - 2.0 * math.pi if d > math.pi else d


def check_reset(pose: Pose2D, linear_speed: float, angular_speed: float, spawn: Pose2D, pos_tol_m: float = 0.05,
                yaw_tol_rad: float = 0.05, speed_tol: float = 0.02) -> ResetCheck:
    """Is the robot (ground-truth pose and speed) back at the spawn and at rest after a reset?"""
    err = math.hypot(pose.x - spawn.x, pose.y - spawn.y)
    yaw_err = angle_diff(pose.yaw, spawn.yaw)
    reasons = []
    if err > pos_tol_m:
        reasons.append(f"position {err:.3f} m from the spawn (> {pos_tol_m} m)")
    if abs(yaw_err) > yaw_tol_rad:
        reasons.append(f"yaw {yaw_err:+.3f} rad from the spawn (> {yaw_tol_rad} rad)")
    if abs(linear_speed) > speed_tol or abs(angular_speed) > speed_tol:
        reasons.append(f"still moving: |v|={abs(linear_speed):.3f} m/s, |w|={abs(angular_speed):.3f} rad/s "
                       f"(> {speed_tol})")
    return ResetCheck(ok=not reasons, position_error_m=err, yaw_error_rad=yaw_err, linear_speed=linear_speed,
                      angular_speed=angular_speed, reasons=tuple(reasons))


def state_name(code: int) -> str:
    return _STATE_NAMES.get(code, f"unknown({code})")


def state_code(name: str) -> int:
    """Code for a state the tool may request. Quitting (closes Isaac) and the non-controllable states are refused."""
    if name == "quitting":
        raise ValueError("refusing to request STATE_QUITTING: it would quit (close) Isaac Sim")
    if name not in _REQUESTABLE:
        raise ValueError(f"state {name!r} cannot be requested (allowed: {sorted(_REQUESTABLE)})")
    return _REQUESTABLE[name]


def validate_spawn_name(name: str) -> str:
    """Full prim path for an entity this tool may spawn or delete; only direct children of SPAWN_ROOT are allowed."""
    if not name:
        raise ValueError("empty entity name")
    full = name if name.startswith("/") else f"{SPAWN_ROOT}/{name}"
    leaf = full[len(SPAWN_ROOT) + 1:] if full.startswith(SPAWN_ROOT + "/") else ""
    if not leaf or "/" in leaf or leaf in (".", "..") or not leaf.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"entity {name!r} must be a simple name directly under {SPAWN_ROOT}")
    return full
