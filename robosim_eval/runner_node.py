"""ROS side of the D2 runner (robosim_eval.runner): the rclpy node with the /clock and odometry subscriptions, the
NavigateToPose action client, direct access to the action's cancel and result services by goal id (the teardown safety
net), the Nav2 lifecycle/parameter queries and the sim_control entity listing. ROS imports stay inside the methods, so
the runner's logic can be tested without ROS.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional

from robosim_eval.config import BaselineConfig
from robosim_eval.runner_fsm import append_sample
from robosim_eval.sim_adapter import SimControlError

NAV2_NODES = ["map_server", "amcl", "planner_server", "controller_server", "bt_navigator", "behavior_server",
              "smoother_server", "velocity_smoother", "collision_monitor", "waypoint_follower"]  # = check_nav2_ready.sh


class RunNode:
    """rclpy node with the /clock and odometry subscriptions and the NavigateToPose action client."""

    def __init__(self, cfg: BaselineConfig) -> None:
        import rclpy
        from nav2_msgs.action import NavigateToPose
        from nav_msgs.msg import Odometry
        from rclpy.action import ActionClient
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from rosgraph_msgs.msg import Clock
        self.rclpy = rclpy
        self.node = Node("robosim_runner")
        self.sim_time: Optional[float] = None
        self.clock_backward = 0
        self.clock_msgs = 0
        self.odom: List[tuple] = []
        self.feedback_count = 0
        self.last_feedback: Dict[str, Any] = {}
        self._clients: Dict[str, Any] = {}
        self.node.create_subscription(Clock, cfg.topics["clock"].name, self._on_clock, qos_profile_sensor_data)
        self.node.create_subscription(Odometry, cfg.topics["odom"].name, self._on_odom, qos_profile_sensor_data)
        self.nav = ActionClient(self.node, NavigateToPose, "/navigate_to_pose")
        self.NavigateToPose = NavigateToPose

    def _on_clock(self, msg) -> None:
        t = msg.clock.sec + msg.clock.nanosec * 1e-9
        if self.sim_time is not None and t < self.sim_time:
            self.clock_backward += 1
        self.sim_time = t
        self.clock_msgs += 1

    def _on_odom(self, msg) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        tw = msg.twist.twist
        append_sample(self.odom, (t, math.hypot(tw.linear.x, tw.linear.y), abs(tw.angular.z)), 400)

    def on_feedback(self, fb) -> None:
        self.feedback_count += 1
        f = fb.feedback
        self.last_feedback = {"distance_remaining": f.distance_remaining, "recoveries": f.number_of_recoveries}

    def spin(self, seconds: float = 0.05) -> None:
        self.rclpy.spin_once(self.node, timeout_sec=seconds)

    def new_goal_uuid(self):
        """The goal id is chosen here, before sending, so a goal whose response never arrives can still be canceled."""
        from unique_identifier_msgs.msg import UUID
        return UUID(uuid=list(os.urandom(16)))

    def _client(self, srv_type, name: str):
        if name not in self._clients:
            self._clients[name] = self.node.create_client(srv_type, name)
        return self._clients[name]

    def cancel_by_id(self, uuid: bytes):
        """CancelGoal for one goal id on the action's own service (action_msgs); None while the service is not ready."""
        from action_msgs.srv import CancelGoal
        cli = self._client(CancelGoal, "/navigate_to_pose/_action/cancel_goal")
        if not cli.service_is_ready():
            return None
        req = CancelGoal.Request()
        req.goal_info.goal_id.uuid = list(uuid)
        return cli.call_async(req)

    def result_by_id(self, uuid: bytes):
        """GetResult for one goal id: status UNKNOWN (0) at once for a goal the server does not know, otherwise the
        answer comes when the goal is terminal. None while the service is not ready."""
        srv = self.NavigateToPose.Impl.GetResultService
        cli = self._client(srv, "/navigate_to_pose/_action/get_result")
        if not cli.service_is_ready():
            return None
        req = srv.Request()
        req.goal_id.uuid = list(uuid)
        return cli.call_async(req)

    def list_entities(self, pattern: str, timeout: float = 15.0) -> List[str]:
        """Prim paths matching the regex `pattern` (simulation_interfaces GetEntities, Isaac sim_control)."""
        from simulation_interfaces.srv import GetEntities
        cli = self._client(GetEntities, "/get_entities")
        if not cli.wait_for_service(timeout_sec=timeout):
            raise SimControlError(f"/get_entities: service not available within {timeout} s")
        req = GetEntities.Request()
        req.filters.filter = pattern
        fut = cli.call_async(req)
        self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
        if not fut.done() or fut.result() is None:
            raise SimControlError(f"/get_entities: no response within {timeout} s")
        res = fut.result()
        if res.result.result != 1:
            raise SimControlError(f"/get_entities: result {res.result.result} {res.result.error_message!r}",
                                  code=res.result.result)
        return list(res.entities)

    def get_param(self, node_name: str, name: str, timeout: float = 5.0) -> Any:
        """Current value of one parameter of a running node (GetParameters service); None when unavailable."""
        from rcl_interfaces.srv import GetParameters
        from rclpy.parameter import parameter_value_to_python
        cli = self.node.create_client(GetParameters, f"/{node_name}/get_parameters")
        try:
            if not cli.wait_for_service(timeout_sec=timeout):
                return None
            fut = cli.call_async(GetParameters.Request(names=[name]))
            self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
            values = fut.result().values if fut.done() and fut.result() is not None else []
            return parameter_value_to_python(values[0]) if values else None
        finally:
            self.node.destroy_client(cli)

    def lifecycle_active(self, timeout: float = 1.0) -> List[str]:
        """Names of the Nav2 lifecycle nodes that are not (yet) active."""
        from lifecycle_msgs.srv import GetState
        pending = []
        for name in NAV2_NODES:
            cli = self.node.create_client(GetState, f"/{name}/get_state")
            ok = False
            if cli.wait_for_service(timeout_sec=timeout):
                fut = cli.call_async(GetState.Request())
                self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
                ok = fut.done() and fut.result() is not None and fut.result().current_state.label == "active"
            self.node.destroy_client(cli)
            if not ok:
                pending.append(name)
        return pending
