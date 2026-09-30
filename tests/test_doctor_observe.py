"""Fixed-input tests of doctor.observe() against an in-process fake rclpy (no DDS, no ROS domain, virtual time).

The fake graph behaves like rmw_dds_common: get_topic_names_and_types() lists, per topic, the sorted set of the types of
every endpoint, the doctor's own subscriptions included, while get_publishers_info_by_topic() lists publishers only.
A subscription only receives messages from publishers of its own type, as DDS type matching does.
"""
from __future__ import annotations

import math
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Tuple

import pytest

from robosim_eval import doctor
from robosim_eval.config import load_config
from robosim_eval.doctor_checks import EXIT_DEGRADED, EXIT_ENV, EXIT_HEALTHY, EXIT_NOT_ADVANCING, EnvFacts, evaluate

CONFIG = """
env: {rmw: rmw_fastrtps_cpp, domain_id: "0", ros_distro: jazzy, require_dds_profile: true}
topics:
  clock: {name: /clock, type: rosgraph_msgs/msg/Clock}
  odom: {name: /chassis/odom, type: nav_msgs/msg/Odometry}
doctor:
  discovery_timeout_s: 5
  window_s: 3
  clock_stall_s: 2
  min_sim_progress_s: 0.2
  streams:
    odom: {min_rate_hz: 8, max_age_s: 2}
"""
NO_ENV_CHECK = EnvFacts(rmw=None, domain_id=None, dds_profile_exists=False, ros_distro=None)


def _stamp(sim_s: float) -> types.SimpleNamespace:
    return types.SimpleNamespace(sec=int(sim_s), nanosec=int((sim_s - int(sim_s)) * 1e9))


@dataclass
class FakePublisher:
    topic: str
    msg_type: str
    hz: float
    make: Callable[[float], Any]


def clock_pub(msg_type: str = "rosgraph_msgs/msg/Clock") -> FakePublisher:
    return FakePublisher("/clock", msg_type, 20.0, lambda sim: types.SimpleNamespace(clock=_stamp(sim)))


def odom_pub(msg_type: str = "nav_msgs/msg/Odometry") -> FakePublisher:
    return FakePublisher("/chassis/odom", msg_type, 20.0,
                         lambda sim: types.SimpleNamespace(header=types.SimpleNamespace(stamp=_stamp(sim))))


class FakeWorld:
    """Virtual wall clock plus the publishers; spin_once() advances time and delivers type-matched messages."""

    def __init__(self, publishers: List[FakePublisher], rtf: float = 0.32) -> None:
        self.now, self.t0, self.rtf = 1000.0, 1000.0, rtf
        self.publishers = publishers
        self.subs: List[Tuple[str, str, Callable[[Any], None]]] = []

    def monotonic(self) -> float:
        return self.now

    def spin_once(self, _node: Any, timeout_sec: float) -> None:
        start, self.now = self.now, self.now + timeout_sec
        for pub in self.publishers:
            first = math.floor((start - self.t0) * pub.hz) + 1
            last = math.floor((self.now - self.t0) * pub.hz)
            for n in range(first, last + 1):
                msg = pub.make(n / pub.hz * self.rtf)
                for topic, msg_type, cb in self.subs:
                    if topic == pub.topic and msg_type == pub.msg_type:
                        cb(msg)


def install_fake_ros(monkeypatch: pytest.MonkeyPatch, world: FakeWorld) -> None:
    def msg_class(type_name: str) -> type:
        return type(type_name.rsplit("/", 1)[-1], (), {"TYPE": type_name})

    class FakeNode:
        def __init__(self, _name: str) -> None:
            pass

        def create_subscription(self, cls: type, topic: str, cb: Callable[[Any], None], _qos: Any) -> None:
            world.subs.append((topic, cls.TYPE, cb))

        def get_topic_names_and_types(self) -> List[Tuple[str, List[str]]]:
            graph: dict = {}
            for p in world.publishers:
                graph.setdefault(p.topic, set()).add(p.msg_type)
            for topic, msg_type, _ in world.subs:
                graph.setdefault(topic, set()).add(msg_type)
            return [(t, sorted(ts)) for t, ts in graph.items()]

        def count_publishers(self, topic: str) -> int:
            return sum(p.topic == topic for p in world.publishers)

        def get_publishers_info_by_topic(self, topic: str) -> list:
            return [types.SimpleNamespace(topic_type=p.msg_type, node_name="fake", node_namespace="/")
                    for p in world.publishers if p.topic == topic]

        def destroy_node(self) -> None:
            pass

    modules = {
        "rclpy": dict(init=lambda: None, shutdown=lambda: None, spin_once=world.spin_once),
        "rclpy.node": dict(Node=FakeNode),
        "rclpy.qos": dict(QoSProfile=lambda **kw: kw, DurabilityPolicy=types.SimpleNamespace(VOLATILE=2),
                          HistoryPolicy=types.SimpleNamespace(KEEP_LAST=1),
                          ReliabilityPolicy=types.SimpleNamespace(BEST_EFFORT=2)),
        "nav_msgs": {}, "rosgraph_msgs": {}, "sensor_msgs": {}, "tf2_msgs": {},
        "nav_msgs.msg": dict(Odometry=msg_class("nav_msgs/msg/Odometry")),
        "rosgraph_msgs.msg": dict(Clock=msg_class("rosgraph_msgs/msg/Clock")),
        "sensor_msgs.msg": dict(PointCloud2=msg_class("sensor_msgs/msg/PointCloud2")),
        "tf2_msgs.msg": dict(TFMessage=msg_class("tf2_msgs/msg/TFMessage")),
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(doctor, "time", types.SimpleNamespace(monotonic=world.monotonic))


def observe_and_judge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publishers: List[FakePublisher]):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(CONFIG, encoding="utf-8")
    cfg = load_config(cfg_path)
    install_fake_ros(monkeypatch, FakeWorld(publishers))
    obs = doctor.observe(cfg, window_s=3.0, discovery_timeout_s=5.0)
    rep = evaluate(obs, cfg.doctor.thresholds, {k: t.msg_type for k, t in cfg.topics.items()}, NO_ENV_CHECK)
    return obs, rep


def test_fake_graph_with_the_right_types_is_healthy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    obs, rep = observe_and_judge(tmp_path, monkeypatch, [clock_pub(), odom_pub()])
    assert rep.exit_code == EXIT_HEALTHY, rep.reasons
    assert obs.clock_types == ("rosgraph_msgs/msg/Clock",)
    assert obs.streams["odom"].msg_types == ("nav_msgs/msg/Odometry",)


def test_publisher_type_sorting_after_the_expected_type_is_an_interface_error(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch):
    # the graph lists [nav_msgs/msg/Odometry (the doctor's own subscription), sensor_msgs/msg/Imu]: the old doctor
    # read the first entry and judged 12 'publisher present but no message'
    obs, rep = observe_and_judge(tmp_path, monkeypatch, [clock_pub(), odom_pub("sensor_msgs/msg/Imu")])
    assert rep.exit_code == EXIT_ENV and rep.exit_code != EXIT_DEGRADED
    assert any("odom" in r and "sensor_msgs/msg/Imu" in r for r in rep.reasons)
    assert obs.streams["odom"].msg_types == ("sensor_msgs/msg/Imu",)


def test_clock_publisher_of_another_type_is_an_interface_error_not_a_pause(tmp_path: Path,
                                                                            monkeypatch: pytest.MonkeyPatch):
    obs, rep = observe_and_judge(tmp_path, monkeypatch, [clock_pub("std_msgs/msg/Float64"), odom_pub()])
    assert rep.exit_code == EXIT_ENV and rep.exit_code != EXIT_NOT_ADVANCING
    assert any("clock" in r and "std_msgs/msg/Float64" in r for r in rep.reasons)
    assert obs.clock_types == ("std_msgs/msg/Float64",)


def test_topic_without_publisher_has_no_type_even_though_the_doctor_subscribes(tmp_path: Path,
                                                                                 monkeypatch: pytest.MonkeyPatch):
    obs, rep = observe_and_judge(tmp_path, monkeypatch, [clock_pub()])
    assert not obs.streams["odom"].present and obs.streams["odom"].msg_types == ()
    assert rep.streams["odom"].status == "missing"
