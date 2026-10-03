"""D1 doctor: observe /clock and the required streams for a bounded window, then judge them (doctor_checks.evaluate).

Run in WSL through scripts/wsl/doctor.sh (it sources the ROS and Fast DDS environment), or directly:
  python3 -m robosim_eval.doctor [--config configs/baseline.yaml] [--out DIR] [--window S]
Exit codes: 0 healthy, 10 simulation not advancing, 11 simulation data missing, 12 degraded, 13 environment or
interface error, 2 usage/config error, 1 internal error. Run time is bounded: at most discovery_timeout_s to find the
topics plus window_s of observation (the window ends early once /clock has stalled for clock_stall_s; it is skipped
when /clock has no publisher at all), plus about 3 s of Python/rclpy start-up and shutdown (13 s with the baseline).
--window must be finite, at least clock_stall_s and leave room under doctor.sh's 60 s cap
(doctor_checks.window_problem).
The environment (RMW, domain, DDS profile, ROS distro, an installed RMW library) is checked before any ROS use; a
mismatch, a missing rclpy or an rclpy that cannot start is 13, and a config error is 2 with a one-line message.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from robosim_eval.config import BaselineConfig, load_config
from robosim_eval.doctor_checks import (
    DoctorReport,
    EnvFacts,
    Observation,
    StreamObservation,
    env_reasons,
    evaluate,
    not_observed_report,
    window_problem,
)

logger = logging.getLogger("robosim_eval.doctor")
REPO = Path(__file__).resolve().parents[1]
EXIT_USAGE, EXIT_INTERNAL = 2, 1


class RosStartError(RuntimeError):
    """rclpy could not start (rclpy.init or the node failed), e.g. ROS_DOMAIN_ID is not a number: exit 13."""


def rmw_problems(rmw: Optional[str]) -> List[str]:
    """Environment reasons found before importing rclpy: rcl ends the whole process with status 1, without a Python
    exception, when RMW_IMPLEMENTATION names a library that is not installed. Unset means the ROS default RMW."""
    if not rmw:
        return []
    try:
        from ament_index_python import get_resources
    except ImportError:
        return []  # no ROS Python environment at all: importing rclpy fails next and is reported as 13
    try:
        installed = get_resources("rmw_typesupport")
    except OSError as exc:  # AMENT_PREFIX_PATH not set: the ROS environment was not sourced
        return [f"cannot read the ament index ({exc}); source the ROS 2 environment"]
    if rmw not in installed:
        return [f"RMW_IMPLEMENTATION {rmw!r} is not installed (ament index lists {sorted(installed)})"]
    return []


def current_env() -> EnvFacts:
    """Environment facts; an unset ROS_DOMAIN_ID means domain 0 for ROS 2."""
    profile = os.environ.get("FASTRTPS_DEFAULT_PROFILES_FILE", "")
    return EnvFacts(rmw=os.environ.get("RMW_IMPLEMENTATION"), domain_id=os.environ.get("ROS_DOMAIN_ID", "0"),
                    dds_profile_exists=bool(profile) and Path(profile).is_file(),
                    ros_distro=os.environ.get("ROS_DISTRO"))


def _stamp(header) -> float:
    return header.stamp.sec + header.stamp.nanosec * 1e-9


def observe(cfg: BaselineConfig, window_s: float, discovery_timeout_s: float) -> Observation:
    """Discover the configured topics, then record receive times and stamps for one bounded window."""
    import rclpy  # imported here so the pure logic and the CLI help work without a ROS environment
    from nav_msgs.msg import Odometry
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import PointCloud2
    from tf2_msgs.msg import TFMessage

    classes = {"rosgraph_msgs/msg/Clock": Clock, "nav_msgs/msg/Odometry": Odometry,
               "tf2_msgs/msg/TFMessage": TFMessage, "sensor_msgs/msg/PointCloud2": PointCloud2}
    wanted = ["clock"] + [k for k in cfg.doctor.thresholds.streams]
    stall_s = cfg.doctor.thresholds.clock_stall_s
    qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
                     history=HistoryPolicy.KEEP_LAST, depth=50)  # best effort matches reliable and best-effort pubs
    try:
        rclpy.init()
    except RuntimeError as exc:  # rclpy's RCLError, e.g. ROS_DOMAIN_ID is not an integral number
        raise RosStartError(f"rclpy.init failed: {exc}") from exc
    try:
        node = Node("robosim_doctor")
    except RuntimeError as exc:
        rclpy.shutdown()
        raise RosStartError(f"creating the doctor node failed: {exc}") from exc
    try:
        clock: List[Tuple[float, float]] = []
        samples: Dict[str, List[Tuple[float, Optional[float]]]] = {k: [] for k in wanted if k != "clock"}

        def on_clock(msg) -> None:
            clock.append((time.monotonic(), msg.clock.sec + msg.clock.nanosec * 1e-9))

        def on_header(key: str):
            return lambda msg: samples[key].append((time.monotonic(), _stamp(msg.header)))

        def on_tf(key: str):
            spec = cfg.topics[key]

            def cb(msg) -> None:
                for tr in msg.transforms:
                    if tr.header.frame_id.lstrip("/") == spec.parent and tr.child_frame_id.lstrip("/") == spec.child:
                        samples[key].append((time.monotonic(), _stamp(tr.header)))
                        return
            return cb

        # subscriptions first, so DDS endpoint matching overlaps with discovery; samples before the window are dropped
        node.create_subscription(Clock, cfg.topics["clock"].name, on_clock, qos)
        for key in samples:
            spec = cfg.topics[key]
            cls = classes.get(spec.msg_type)
            if cls is None:
                raise ValueError(f"topics.{key}: unsupported message type {spec.msg_type}")
            callback = on_tf(key) if cls is TFMessage and spec.child else on_header(key)
            node.create_subscription(cls, spec.name, callback, qos)

        # Publishers only: the graph's topic types also list the doctor's own subscriptions, which hid a publisher of
        # another type (review round 1). DDS never delivers such a publisher's messages to the subscription.
        deadline = time.monotonic() + discovery_timeout_s
        while True:
            rclpy.spin_once(node, timeout_sec=0.1)
            publishers = {k: node.get_publishers_info_by_topic(cfg.topics[k].name) for k in wanted}
            present = {k: bool(publishers[k]) for k in wanted}
            if all(present.values()) or time.monotonic() >= deadline:
                break
        types = {k: tuple(sorted({p.topic_type for p in publishers[k]})) for k in wanted}

        start = time.monotonic()
        end = start + (window_s if present["clock"] else 0.0)
        while time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            now = time.monotonic()
            last = clock[-1][0] if clock else start
            if now - last > stall_s:
                break  # the clock has stalled long enough to judge; do not wait out the window
        stop = time.monotonic()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    streams = {k: StreamObservation(present=present[k], msg_types=types[k],
                                    samples=tuple(x for x in v if x[0] >= start))
               for k, v in samples.items()}
    return Observation(window_start=start, window_end=stop, clock_present=present["clock"], clock_types=types["clock"],
                       clock=tuple(x for x in clock if x[0] >= start), streams=streams, env=current_env())


def format_report(cfg: BaselineConfig, rep: DoctorReport) -> str:
    if not rep.observed:
        lines = ["ROS graph not observed: the environment is not usable"] + [f"reason: {r}" for r in rep.reasons]
        return "\n".join(lines + [f"verdict: {rep.verdict} (exit {rep.exit_code})"])
    c = rep.clock
    rtf = f"{c.rtf:.2f}" if c.rtf is not None else "-"
    age = f"{c.last_age_s:.2f} s ago" if c.last_age_s is not None else "never"
    lines = [f"clock  {cfg.topics['clock'].name:<32} {'present' if c.present else 'NO PUBLISHER':<12} "
             f"{c.count} msgs {c.rate_hz:6.2f} Hz  sim +{c.sim_progress_s:.3f} s  RTF {rtf}  last {age}"]
    for key, st in rep.streams.items():
        spec = cfg.topics[key]
        name = spec.name + (f" {spec.parent}->{spec.child}" if spec.child else "")
        gap = f"{st.max_gap_s:.3f}" if st.max_gap_s is not None else "-"
        last = f"{st.last_age_s:.2f}" if st.last_age_s is not None else "-"
        lag = f"{st.stamp_lag_s:.3f}" if st.stamp_lag_s is not None else "-"
        lines.append(f"{key:<6} {name:<32} {st.status:<12} {st.count} msgs {st.rate_hz:6.2f} Hz  max gap {gap} s  "
                     f"last {last} s ago  stamp lag {lag} s")
    lines += [f"reason: {r}" for r in rep.reasons] + [f"warning: {w}" for w in rep.warnings]
    lines.append(f"verdict: {rep.verdict} (exit {rep.exit_code}); window {rep.window_s:.2f} s wall")
    return "\n".join(lines)


def judge(cfg: BaselineConfig, window: float, expected_env: EnvFacts, env: EnvFacts) -> Optional[DoctorReport]:
    """The report for this run; None for a config error found while observing (unsupported message type)."""
    reasons = env_reasons(env, expected_env) + rmw_problems(env.rmw)
    if reasons:
        return not_observed_report(reasons, cfg.doctor.thresholds)  # before any ROS use
    try:
        obs = observe(cfg, window, cfg.doctor.discovery_timeout_s)
    except ImportError as exc:
        return not_observed_report([f"ROS 2 Python environment not available: {exc}"], cfg.doctor.thresholds)
    except RosStartError as exc:
        return not_observed_report([f"ROS 2 could not start: {exc}"], cfg.doctor.thresholds)
    except ValueError as exc:
        logger.error("config error: %s", exc)
        return None
    types = {k: t.msg_type for k, t in cfg.topics.items()}
    return evaluate(obs, cfg.doctor.thresholds, types, expected_env)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="RoboSim Eval D1 doctor (bounded ROS 2 data check)")
    parser.add_argument("--config", default=str(REPO / "configs" / "baseline.yaml"))
    parser.add_argument("--out", help="directory for doctor-<time>.json (created if missing)")
    parser.add_argument("--window", type=float, help="override doctor.window_s (wall seconds)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    started = datetime.datetime.now().astimezone()
    try:
        cfg = load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("config error: %s", " ".join(str(exc).split()))
        return EXIT_USAGE
    window = args.window if args.window is not None else cfg.doctor.window_s
    problem = window_problem(window, cfg.doctor.thresholds.clock_stall_s, cfg.doctor.discovery_timeout_s)
    if problem:
        logger.error("usage error: --window: %s", problem)
        return EXIT_USAGE
    expected_env = EnvFacts(rmw=cfg.env.rmw, domain_id=cfg.env.domain_id,
                            dds_profile_exists=cfg.env.require_dds_profile, ros_distro=cfg.env.ros_distro)
    env = current_env()
    sys.stdout.write(f"doctor {started.isoformat(timespec='seconds')} config={args.config} window={window}s "
                     f"discovery<={cfg.doctor.discovery_timeout_s}s\n"
                     f"env: RMW={env.rmw} ROS_DOMAIN_ID={env.domain_id} ROS_DISTRO={env.ros_distro} "
                     f"FASTRTPS_DEFAULT_PROFILES_FILE={os.environ.get('FASTRTPS_DEFAULT_PROFILES_FILE', '')} "
                     f"(exists={env.dds_profile_exists})\n")
    rep = judge(cfg, window, expected_env, env)
    if rep is None:
        return EXIT_USAGE
    sys.stdout.write(format_report(cfg, rep) + "\n")
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"doctor-{started.strftime('%Y%m%d-%H%M%S')}.json"
        payload = {"started": started.isoformat(), "config": str(args.config), "window_s_requested": window,
                   "env": dataclasses.asdict(env), "report": rep.to_dict()}
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        sys.stdout.write(f"written {path}\n")
    return rep.exit_code


if __name__ == "__main__":
    sys.exit(main())
