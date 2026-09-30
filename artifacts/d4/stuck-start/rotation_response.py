"""Stuck-start check: does the robot turn in place when given DWB's smallest rotation sample (0.7/19 rad/s)?

With Nav2 NOT running (nothing else may publish /cmd_vel), for each angular speed: reset the scene through
sim_control, wait until settled, publish /cmd_vel (0 m/s, w rad/s) at 20 Hz for --hold wall seconds, publish zero
for 1 s, and compare the ground-truth yaw of the chassis (sim_control /get_entity_state) before and after.
Run in WSL from the repo root with the ROS environment sourced (see run_rotation_response.sh):
  python3 artifacts/d4/stuck-start/rotation_response.py [--hold 20] [--speeds 0.0368,0.1105,0.2579]
Prints one JSON line per speed; exit 0 when every measurement completed, 2 when Nav2 appears to be running.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from robosim_eval.config import load_config  # noqa: E402
from robosim_eval.sim_adapter import SimAdapter  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hold", type=float, default=20.0)
    p.add_argument("--speeds", default=f"{0.7 / 19:.4f},{3 * 0.7 / 19:.4f},{7 * 0.7 / 19:.4f}")
    a = p.parse_args()
    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    rclpy.init()
    node = Node("robosim_rotation_response")
    clock = {"t": None}
    node.create_subscription(Clock, "/clock", lambda m: clock.update(t=m.clock.sec + m.clock.nanosec * 1e-9),
                             qos_profile_sensor_data)
    try:
        names = {n for n, _ in node.get_node_names_and_namespaces()}
        time.sleep(2.0)
        names |= {n for n, _ in node.get_node_names_and_namespaces()}
        if {"controller_server", "velocity_smoother", "bt_navigator"} & names:
            print(json.dumps({"error": "Nav2 nodes are running; stop Nav2 first", "nodes": sorted(names)}))
            return 2
        cfg = load_config(REPO / "configs" / "baseline.yaml")
        sim = SimAdapter(node)
        pub = node.create_publisher(Twist, "/cmd_vel", 10)
        for w in [float(s) for s in a.speeds.split(",")]:
            sim.reset()
            end = time.monotonic() + 4.0
            while time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.1)
            before, t_before = sim.entity_state(cfg.sim.robot_entity), clock["t"]
            msg = Twist()
            msg.angular.z = w
            peak = 0.0
            end = time.monotonic() + a.hold
            while time.monotonic() < end:
                pub.publish(msg)
                rclpy.spin_once(node, timeout_sec=0.05)
            mid = sim.entity_state(cfg.sim.robot_entity)
            peak = abs(mid["angular_speed"])
            msg.angular.z = 0.0
            end = time.monotonic() + 1.0
            while time.monotonic() < end:
                pub.publish(msg)
                rclpy.spin_once(node, timeout_sec=0.05)
            after, t_after = sim.entity_state(cfg.sim.robot_entity), clock["t"]
            dyaw = math.atan2(math.sin(after["yaw"] - before["yaw"]), math.cos(after["yaw"] - before["yaw"]))
            dt = None if t_before is None or t_after is None else round(t_after - t_before, 3)
            print(json.dumps({"cmd_angular_radps": w, "hold_wall_s": a.hold, "yaw_before": before["yaw"],
                              "yaw_after": after["yaw"], "yaw_change_rad": dyaw,
                              "gt_angular_speed_at_end_of_hold": peak,
                              "moved_m": math.hypot(after["x"] - before["x"], after["y"] - before["y"]),
                              "sim_elapsed_s": dt}), flush=True)
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
