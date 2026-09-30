"""Isaac Sim control over ROS 2 simulation_interfaces (isaacsim.ros2.sim_control, enabled by start_isaac_ros2.ps1).

Run in WSL through scripts/wsl/sim.sh (it sources the ROS and Fast DDS environment), or directly:
  python3 -m robosim_eval.sim_adapter state | play | pause | stop | load [<uri>] | reset | pose [<entity>]
                                      | reset-check | spawn-box <name> <x> <y> [<yaw>] | delete <name>
Every service call has a timeout; each command prints one JSON line. Exit 0 ok; 3 service unavailable, timed out or
returned an error; 4 reset-check failed (robot not back at the spawn or still moving); 2 usage/config error.
Guards (robosim_eval.sim_math): STATE_QUITTING is never requested; only entities under SPAWN_ROOT are spawned/deleted.
Ground truth: GetEntityState on the chassis rigid body returns the live world pose and twist; its header stamp is zero,
so callers pair it with a /clock sample when they need a time.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from robosim_eval.config import load_config
from robosim_eval.sim_math import Pose2D, check_reset, quat_from_yaw, state_code, state_name, validate_spawn_name, \
    yaw_from_quat

REPO = Path(__file__).resolve().parents[1]
RESULT_OK = 1
ALREADY_IN_TARGET_STATE = 101


class SimControlError(RuntimeError):
    """A sim_control service was unavailable, timed out, or returned a non-OK result. `code` is the
    simulation_interfaces Result code when the service answered with one (e.g. 2 RESULT_NOT_FOUND), else None."""

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        super().__init__(message)
        self.code: Optional[int] = code


class SimAdapter:
    def __init__(self, node, timeout_s: float = 15.0) -> None:
        self.node = node
        self.timeout_s = timeout_s
        self._clients: Dict[str, Any] = {}

    def _call(self, srv_cls, name: str, request, timeout: Optional[float] = None):
        import rclpy
        timeout = timeout or self.timeout_s
        client = self._clients.get(name)
        if client is None:
            client = self._clients[name] = self.node.create_client(srv_cls, name)
        if not client.wait_for_service(timeout_sec=timeout):
            raise SimControlError(f"{name}: service not available within {timeout} s (is sim_control enabled?)")
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        if not future.done():
            raise SimControlError(f"{name}: no response within {timeout} s")
        return future.result()

    @staticmethod
    def _require_ok(name: str, result, extra_ok: Sequence[int] = ()) -> None:
        if result.result != RESULT_OK and result.result not in extra_ok:
            raise SimControlError(f"{name}: result {result.result} {result.error_message!r}", code=result.result)

    def get_state(self) -> str:
        from simulation_interfaces.srv import GetSimulationState
        resp = self._call(GetSimulationState, "/get_simulation_state", GetSimulationState.Request())
        self._require_ok("/get_simulation_state", resp.result)
        return state_name(resp.state.state)

    def set_state(self, name: str) -> str:
        from simulation_interfaces.srv import SetSimulationState
        req = SetSimulationState.Request()
        req.state.state = state_code(name)  # raises for quitting and non-controllable states
        resp = self._call(SetSimulationState, "/set_simulation_state", req)
        self._require_ok("/set_simulation_state", resp.result, extra_ok=(ALREADY_IN_TARGET_STATE,))
        return self.get_state()

    def load_world(self, uri: str, timeout: float = 180.0) -> str:
        from simulation_interfaces.srv import LoadWorld
        req = LoadWorld.Request()
        req.uri = uri
        resp = self._call(LoadWorld, "/load_world", req, timeout=timeout)
        self._require_ok("/load_world", resp.result)
        return self.get_state()

    def reset(self, timeout: float = 60.0) -> str:
        from simulation_interfaces.srv import ResetSimulation
        resp = self._call(ResetSimulation, "/reset_simulation", ResetSimulation.Request(), timeout=timeout)
        self._require_ok("/reset_simulation", resp.result)
        return self.get_state()

    def entity_state(self, entity: str) -> Dict[str, Any]:
        from simulation_interfaces.srv import GetEntityState
        req = GetEntityState.Request()
        req.entity = entity
        resp = self._call(GetEntityState, "/get_entity_state", req)
        self._require_ok("/get_entity_state", resp.result)
        p, q, t = resp.state.pose.position, resp.state.pose.orientation, resp.state.twist
        return {"entity": entity, "frame": resp.state.header.frame_id, "x": p.x, "y": p.y, "z": p.z,
                "yaw": yaw_from_quat(q.x, q.y, q.z, q.w), "linear_speed": math.hypot(t.linear.x, t.linear.y),
                "angular_speed": abs(t.angular.z), "received_wall": time.time()}

    def spawn_box(self, name: str, x: float, y: float, yaw: float, uri: str) -> str:
        from simulation_interfaces.srv import SpawnEntity
        full = validate_spawn_name(name)
        req = SpawnEntity.Request()
        req.name, req.uri, req.allow_renaming = full, uri, False
        req.initial_pose.pose.position.x, req.initial_pose.pose.position.y = x, y
        qx, qy, qz, qw = quat_from_yaw(yaw)
        o = req.initial_pose.pose.orientation
        o.x, o.y, o.z, o.w = qx, qy, qz, qw
        resp = self._call(SpawnEntity, "/spawn_entity", req)
        self._require_ok("/spawn_entity", resp.result)
        return resp.entity_name or full

    def delete(self, name: str) -> None:
        from simulation_interfaces.srv import DeleteEntity
        req = DeleteEntity.Request()
        req.entity = validate_spawn_name(name)
        resp = self._call(DeleteEntity, "/delete_entity", req)
        self._require_ok("/delete_entity", resp.result)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Isaac sim_control client (simulation_interfaces)")
    p.add_argument("--config", default=str(REPO / "configs" / "baseline.yaml"))
    p.add_argument("command", choices=["state", "play", "pause", "stop", "load", "reset", "pose", "reset-check",
                                       "spawn-box", "delete"])
    p.add_argument("args", nargs="*")
    a = p.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except (OSError, ValueError) as exc:
        print(json.dumps({"command": a.command, "error": f"config: {exc}"}))
        return 2
    if cfg.sim is None:
        print(json.dumps({"command": a.command, "error": "config has no sim section"}))
        return 2
    import rclpy
    from rclpy.node import Node
    rclpy.init()
    node = Node("robosim_sim_adapter")
    sim = SimAdapter(node)
    out: Dict[str, Any] = {"command": a.command}
    rc = 0
    try:
        if a.command == "state":
            out["state"] = sim.get_state()
        elif a.command in ("play", "pause", "stop"):
            out["state"] = sim.set_state({"play": "playing", "pause": "paused", "stop": "stopped"}[a.command])
        elif a.command == "load":
            out["uri"] = a.args[0] if a.args else cfg.sim.world_uri
            out["state"] = sim.load_world(out["uri"])
        elif a.command == "reset":
            out["state"] = sim.reset()
        elif a.command == "pose":
            out.update(sim.entity_state(a.args[0] if a.args else cfg.sim.robot_entity))
        elif a.command == "reset-check":
            st = sim.entity_state(cfg.sim.robot_entity)
            res = check_reset(Pose2D(st["x"], st["y"], st["yaw"]), st["linear_speed"], st["angular_speed"],
                              cfg.sim.spawn, cfg.sim.reset_position_m, cfg.sim.reset_yaw_rad, cfg.sim.reset_speed)
            out.update(st, ok=res.ok, position_error_m=res.position_error_m, yaw_error_rad=res.yaw_error_rad,
                       reasons=list(res.reasons))
            rc = 0 if res.ok else 4
        elif a.command == "spawn-box":
            name, x, y = a.args[0], float(a.args[1]), float(a.args[2])
            yaw = float(a.args[3]) if len(a.args) > 3 else 0.0
            if not cfg.sim.obstacle_usd:
                raise ValueError("sim.obstacle_usd is not configured")
            out["entity"] = sim.spawn_box(name, x, y, yaw, cfg.sim.obstacle_usd)
        elif a.command == "delete":
            sim.delete(a.args[0])
            out["deleted"] = a.args[0]
    except (IndexError, ValueError) as exc:
        out["error"] = f"usage: {exc}"
        rc = 2
    except SimControlError as exc:
        out["error"] = str(exc)
        rc = 3
    finally:
        node.destroy_node()
        rclpy.shutdown()
    print(json.dumps(out))
    return rc


if __name__ == "__main__":
    sys.exit(main())
