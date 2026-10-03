"""Fake Nav2 NavigateToPose action server for the runner's fake-node test (ROS 2 only, no simulator, no Nav2).

Run in WSL with the ROS environment sourced, on the isolated ROS_DOMAIN_ID used by the test:
  python3 tests/ros_fake/fake_nav2.py --mode succeed|abort|never|reject|ignore-cancel [--duration S] [--accept-delay S]
  succeed        accept, publish feedback for --duration s, then SUCCEEDED
  abort          accept, publish feedback for --duration s, then ABORTED (error_code 208, like NO_VALID_PATH)
  never          accept and keep running until the client cancels (cancel is accepted -> CANCELED)
  reject         reject the goal
  ignore-cancel  accept, never finish, and reject every cancel request
  --param NAME=VALUE (repeatable) also runs a node named controller_server with that float parameter declared, for
  the runner's check that a declared Nav2 parameter change is in effect (D5)
  --accept-delay S  answer each goal request only after S s (the runner's acceptance deadline and its teardown safety
  net: a goal accepted after the runner gave up waiting must still be canceled)
"""
from __future__ import annotations

import argparse
import time

import rclpy
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node


class FakeNav2(Node):
    def __init__(self, mode: str, duration: float, accept_delay: float = 0.0) -> None:
        super().__init__("fake_nav2")
        self.mode, self.duration, self.accept_delay = mode, duration, accept_delay
        self.server = ActionServer(self, NavigateToPose, "/navigate_to_pose", execute_callback=self.execute,
                                   goal_callback=self.on_goal, cancel_callback=self.on_cancel,
                                   callback_group=ReentrantCallbackGroup())

    def on_goal(self, _request) -> GoalResponse:
        time.sleep(self.accept_delay)  # blocks this callback only (multi-threaded executor, reentrant group)
        return GoalResponse.REJECT if self.mode == "reject" else GoalResponse.ACCEPT

    def on_cancel(self, _handle) -> CancelResponse:
        return CancelResponse.REJECT if self.mode == "ignore-cancel" else CancelResponse.ACCEPT

    def execute(self, handle):
        t0 = time.monotonic()
        feedback = NavigateToPose.Feedback()
        while True:
            if handle.is_cancel_requested:
                handle.canceled()
                return NavigateToPose.Result()
            elapsed = time.monotonic() - t0
            feedback.distance_remaining = max(0.0, 2.0 - elapsed)
            handle.publish_feedback(feedback)
            if self.mode in ("succeed", "abort") and elapsed >= self.duration:
                result = NavigateToPose.Result()
                if self.mode == "succeed":
                    handle.succeed()
                else:
                    result.error_code, result.error_msg = 208, "fake: no valid path"
                    handle.abort()
                return result
            time.sleep(0.1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mode", required=True, choices=["succeed", "abort", "never", "reject", "ignore-cancel"])
    p.add_argument("--duration", type=float, default=2.0)
    p.add_argument("--lifetime", type=float, default=90.0)
    p.add_argument("--accept-delay", type=float, default=0.0)
    p.add_argument("--param", action="append", default=[])
    a = p.parse_args()
    rclpy.init()
    node = FakeNav2(a.mode, a.duration, a.accept_delay)
    ex = MultiThreadedExecutor()
    ex.add_node(node)
    if a.param:
        controller = Node("controller_server")
        for item in a.param:
            name, value = item.split("=", 1)
            controller.declare_parameter(name, float(value))
        ex.add_node(controller)
    end = time.monotonic() + a.lifetime
    try:
        while rclpy.ok() and time.monotonic() < end:
            ex.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        ex.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
