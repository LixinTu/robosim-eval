"""D1 doctor: observe /clock and the required streams for a bounded window, then judge them (doctor_checks.evaluate).

Run in WSL through scripts/wsl/doctor.sh (it sources the ROS and Fast DDS environment), or directly:
  python3 -m robosim_eval.doctor [--config configs/baseline.yaml] [--out DIR] [--window S]
Exit codes: 0 healthy, 10 simulation not advancing, 11 simulation data missing, 12 degraded, 13 environment or
interface error, 2 usage/config error, 1 internal error. Run time is bounded: at most discovery_timeout_s to find the
topics plus window_s of observation (the window ends early once /clock has stalled for clock_stall_s; it is skipped
when /clock has no publisher at all), plus about 3 s of Python/rclpy start-up and shutdown (13 s with the baseline).
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
    EXIT_ENV,
    DoctorReport,
    EnvFacts,
    Observation,
    StreamObservation,
    evaluate,
)

logger = logging.getLogger("robosim_eval.doctor")
REPO = Path(__file__).resolve().parents[1]
EXIT_USAGE, EXIT_INTERNAL = 2, 1


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
    rclpy.init()
    node = Node("robosim_doctor")
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

        deadline = time.monotonic() + discovery_timeout_s
        while True:
            rclpy.spin_once(node, timeout_sec=0.1)
            graph = dict(node.get_topic_names_and_types())
            present = {k: cfg.topics[k].name in graph and node.count_publishers(cfg.topics[k].name) > 0
                       for k in wanted}
            if all(present.values()) or time.monotonic() >= deadline:
                break
        types = {k: (graph.get(cfg.topics[k].name) or [None])[0] for k in wanted}

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
    streams = {k: StreamObservation(present=present[k], msg_type=types[k], samples=tuple(x for x in v if x[0] >= start))
               for k, v in samples.items()}
    return Observation(window_start=start, window_end=stop, clock_present=present["clock"], clock_type=types["clock"],
                       clock=tuple(x for x in clock if x[0] >= start), streams=streams, env=current_env())


def format_report(cfg: BaselineConfig, rep: DoctorReport) -> str:
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
        logger.error("config error: %s", exc)
        return EXIT_USAGE
    window = args.window if args.window is not None else cfg.doctor.window_s
    expected_env = EnvFacts(rmw=cfg.env.rmw, domain_id=cfg.env.domain_id,
                            dds_profile_exists=cfg.env.require_dds_profile, ros_distro=cfg.env.ros_distro)
    env = current_env()
    sys.stdout.write(f"doctor {started.isoformat(timespec='seconds')} config={args.config} window={window}s "
                     f"discovery<={cfg.doctor.discovery_timeout_s}s\n"
                     f"env: RMW={env.rmw} ROS_DOMAIN_ID={env.domain_id} ROS_DISTRO={env.ros_distro} "
                     f"FASTRTPS_DEFAULT_PROFILES_FILE={os.environ.get('FASTRTPS_DEFAULT_PROFILES_FILE', '')} "
                     f"(exists={env.dds_profile_exists})\n")
    try:
        obs = observe(cfg, window, cfg.doctor.discovery_timeout_s)
    except ImportError as exc:
        logger.error("ROS 2 Python environment not available: %s", exc)
        return EXIT_ENV
    except ValueError as exc:
        logger.error("config error: %s", exc)
        return EXIT_USAGE
    types = {k: t.msg_type for k, t in cfg.topics.items()}
    rep = evaluate(obs, cfg.doctor.thresholds, types, expected_env)
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
