"""Fake Isaac Sim publishers for the doctor's fake-node integration test (ROS 2 only, no simulator).

Run in WSL with the ROS environment sourced, on an isolated ROS_DOMAIN_ID so the real Isaac data is not disturbed:
  python3 tests/ros_fake/fake_isaac.py [--rtf 0.4] [--clock-hz 25] [--odom-hz 25] [--tf-hz 25] [--lidar-hz 2.6]
                                       [--no-lidar] [--pause-after S] [--duration S]
--pause-after S: after S wall seconds stop publishing but keep every publisher alive (like a paused Isaac timeline).
--duration S: exit after S wall seconds (default 60).
"""
from __future__ import annotations

import argparse
import struct
import time

import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import PointCloud2, PointField
from tf2_msgs.msg import TFMessage


class FakeIsaac(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("fake_isaac")
        self.args = args
        self.t0 = time.monotonic()
        self.pub_clock = self.create_publisher(Clock, "/clock", 10)
        self.pub_odom = self.create_publisher(Odometry, "/chassis/odom", 10)
        self.pub_tf = self.create_publisher(TFMessage, "/tf", 10)
        self.pub_lidar = None if args.no_lidar else self.create_publisher(
            PointCloud2, "/front_3d_lidar/lidar_points", 10)
        self.create_timer(1.0 / args.clock_hz, self.on_clock)
        self.create_timer(1.0 / args.odom_hz, self.on_odom)
        self.create_timer(1.0 / args.tf_hz, self.on_tf)
        if self.pub_lidar is not None:
            self.create_timer(1.0 / args.lidar_hz, self.on_lidar)

    def active(self) -> bool:
        return self.args.pause_after is None or time.monotonic() - self.t0 < self.args.pause_after

    def sim(self):
        s = (time.monotonic() - self.t0) * self.args.rtf
        return int(s), int((s - int(s)) * 1e9)

    def on_clock(self) -> None:
        if self.active():
            msg = Clock()
            msg.clock.sec, msg.clock.nanosec = self.sim()
            self.pub_clock.publish(msg)

    def on_odom(self) -> None:
        if self.active():
            msg = Odometry()
            msg.header.stamp.sec, msg.header.stamp.nanosec = self.sim()
            msg.header.frame_id, msg.child_frame_id = "odom", "base_link"
            self.pub_odom.publish(msg)

    def on_tf(self) -> None:
        if self.active():
            tr = TransformStamped()
            tr.header.stamp.sec, tr.header.stamp.nanosec = self.sim()
            tr.header.frame_id, tr.child_frame_id = "odom", "base_link"
            tr.transform.rotation.w = 1.0
            self.pub_tf.publish(TFMessage(transforms=[tr]))

    def on_lidar(self) -> None:
        if self.active():
            msg = PointCloud2()
            msg.header.stamp.sec, msg.header.stamp.nanosec = self.sim()
            msg.header.frame_id = "front_3d_lidar"
            msg.height, msg.width = 1, 10
            msg.fields = [PointField(name=n, offset=4 * i, datatype=PointField.FLOAT32, count=1)
                          for i, n in enumerate("xyz")]
            msg.point_step, msg.row_step, msg.is_dense = 12, 120, True
            msg.data = struct.pack("<30f", *([1.0] * 30))
            self.pub_lidar.publish(msg)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--rtf", type=float, default=0.4)
    p.add_argument("--clock-hz", type=float, default=25.0)
    p.add_argument("--odom-hz", type=float, default=25.0)
    p.add_argument("--tf-hz", type=float, default=25.0)
    p.add_argument("--lidar-hz", type=float, default=2.6)
    p.add_argument("--no-lidar", action="store_true")
    p.add_argument("--pause-after", type=float, default=None)
    p.add_argument("--duration", type=float, default=60.0)
    args = p.parse_args()
    rclpy.init()
    node = FakeIsaac(args)
    try:
        end = time.monotonic() + args.duration
        while rclpy.ok() and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
