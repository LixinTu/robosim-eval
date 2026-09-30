"""Fixed-input tests for the D1 doctor verdict logic (no ROS, no simulator).

The doctor observes /clock and the required sensor streams for a bounded wall-clock window and must:
report real rates and freshness when the simulation is healthy (exit 0), and exit non-zero within bounded time when
the simulation is paused (10), closed or disconnected (11), degraded (12), or the environment/interfaces are wrong (13).
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional, Tuple

import pytest

from robosim_eval.doctor_checks import (
    EXIT_DATA_MISSING,
    EXIT_DEGRADED,
    EXIT_ENV,
    EXIT_HEALTHY,
    EXIT_NOT_ADVANCING,
    DoctorReport,
    DoctorThresholds,
    EnvFacts,
    Observation,
    StreamObservation,
    StreamThresholds,
    evaluate,
    window_problem,
)

W0, W1 = 100.0, 105.0  # observation window in wall seconds

THRESHOLDS = DoctorThresholds(
    clock_stall_s=2.0,
    min_sim_progress_s=0.2,
    streams={
        "odom": StreamThresholds(min_rate_hz=8.0, max_age_s=2.0),
        "tf": StreamThresholds(min_rate_hz=8.0, max_age_s=2.0),
        "lidar": StreamThresholds(min_rate_hz=1.0, max_age_s=2.0),
    },
)
EXPECTED_TYPES = {
    "clock": "rosgraph_msgs/msg/Clock",
    "odom": "nav_msgs/msg/Odometry",
    "tf": "tf2_msgs/msg/TFMessage",
    "lidar": "sensor_msgs/msg/PointCloud2",
}
GOOD_ENV = EnvFacts(rmw="rmw_fastrtps_cpp", domain_id="0", dds_profile_exists=True, ros_distro="jazzy")


def ticks(start: float, end: float, hz: float) -> List[float]:
    """Receive times at a fixed rate in [start, end)."""
    out: List[float] = []
    t = start
    while t < end - 1e-9:
        out.append(round(t, 6))
        t += 1.0 / hz
    return out


def clock_samples(start: float, end: float, hz: float, rtf: float, sim0: float = 500.0) -> List[Tuple[float, float]]:
    return [(t, sim0 + (t - start) * rtf) for t in ticks(start, end, hz)]


def default_sim(t: float) -> float:
    return 500.0 + (t - W0) * 0.4


def stream(times: List[float], name: str, sim_of: Callable[[float], float] = default_sim, present: bool = True,
           msg_type: Optional[str] = None) -> StreamObservation:
    return StreamObservation(present=present, msg_type=msg_type or EXPECTED_TYPES[name],
                             samples=tuple((t, sim_of(t)) for t in times))


def healthy_observation(**overrides) -> Observation:
    streams: Dict[str, StreamObservation] = {
        "odom": stream(ticks(W0, W1, 25.0), "odom"),
        "tf": stream(ticks(W0, W1, 25.0), "tf"),
        "lidar": stream(ticks(W0, W1, 2.6), "lidar"),
    }
    streams.update(overrides.pop("streams", {}))
    kwargs = dict(window_start=W0, window_end=W1, clock_present=True, clock_type=EXPECTED_TYPES["clock"],
                  clock=tuple(clock_samples(W0, W1, 25.0, 0.4)), streams=streams, env=GOOD_ENV)
    kwargs.update(overrides)
    return Observation(**kwargs)


def run(obs: Observation) -> DoctorReport:
    return evaluate(obs, THRESHOLDS, EXPECTED_TYPES, expected_env=GOOD_ENV)


def test_healthy_simulation_exits_zero_and_reports_real_rates_and_freshness():
    rep = run(healthy_observation())
    assert rep.exit_code == EXIT_HEALTHY and rep.verdict == "healthy"
    assert rep.clock.rate_hz == pytest.approx(25.0, rel=0.05)
    assert rep.clock.sim_progress_s == pytest.approx(2.0, abs=0.05)
    assert rep.clock.rtf == pytest.approx(0.4, abs=0.02)
    assert rep.streams["lidar"].rate_hz == pytest.approx(2.6, rel=0.1)
    assert rep.streams["odom"].last_age_s < 0.1
    assert all(s.status == "ok" for s in rep.streams.values())


def test_paused_simulation_with_publishers_but_no_messages_is_not_advancing():
    silent = {n: stream([], n) for n in ("odom", "tf", "lidar")}
    rep = run(healthy_observation(clock=(), streams=silent))
    assert rep.exit_code == EXIT_NOT_ADVANCING and rep.verdict == "sim_not_advancing"
    assert any("clock" in r for r in rep.reasons)


def test_clock_messages_with_frozen_sim_time_are_not_advancing():
    frozen = tuple((t, 230.85) for t in ticks(W0, W1, 25.0))
    rep = run(healthy_observation(clock=frozen))
    assert rep.exit_code == EXIT_NOT_ADVANCING
    assert rep.clock.sim_progress_s == pytest.approx(0.0)


def test_clock_that_stops_during_the_window_is_not_advancing():
    early = tuple(clock_samples(W0, W0 + 1.0, 25.0, 0.4))  # nothing after the first second
    rep = run(healthy_observation(clock=early))
    assert rep.exit_code == EXIT_NOT_ADVANCING
    assert rep.clock.last_age_s == pytest.approx(W1 - (W0 + 0.96), abs=0.05)


def test_closed_simulation_without_any_publisher_is_data_missing():
    absent = {n: stream([], n, present=False) for n in ("odom", "tf", "lidar")}
    rep = run(healthy_observation(clock_present=False, clock=(), streams=absent))
    assert rep.exit_code == EXIT_DATA_MISSING and rep.verdict == "sim_data_missing"


def test_advancing_clock_but_missing_lidar_publisher_is_data_missing():
    rep = run(healthy_observation(streams={"lidar": stream([], "lidar", present=False)}))
    assert rep.exit_code == EXIT_DATA_MISSING
    assert rep.streams["lidar"].status == "missing"
    assert any("lidar" in r for r in rep.reasons)


def test_slow_stream_is_degraded():
    rep = run(healthy_observation(streams={"lidar": stream(ticks(W0, W1, 0.5), "lidar")}))
    assert rep.exit_code == EXIT_DEGRADED and rep.verdict == "degraded"
    assert rep.streams["lidar"].status == "slow"


def test_stale_stream_is_degraded():
    rep = run(healthy_observation(streams={"odom": stream(ticks(W0, W1 - 3.0, 25.0), "odom")}))
    assert rep.exit_code == EXIT_DEGRADED
    assert rep.streams["odom"].status == "stale"
    assert rep.streams["odom"].last_age_s > 2.0


def test_silent_stream_while_clock_advances_is_degraded():
    rep = run(healthy_observation(streams={"tf": stream([], "tf")}))
    assert rep.exit_code == EXIT_DEGRADED
    assert rep.streams["tf"].status == "silent"


def test_wrong_rmw_is_an_environment_error_even_when_data_flows():
    rep = evaluate(healthy_observation(env=EnvFacts("rmw_zenoh_cpp", "0", True, "jazzy")),
                   THRESHOLDS, EXPECTED_TYPES, expected_env=GOOD_ENV)
    assert rep.exit_code == EXIT_ENV and rep.verdict == "env_or_interface_error"
    assert any("RMW" in r for r in rep.reasons)


def test_missing_dds_profile_is_an_environment_error():
    rep = evaluate(healthy_observation(env=EnvFacts("rmw_fastrtps_cpp", "0", False, "jazzy")),
                   THRESHOLDS, EXPECTED_TYPES, expected_env=GOOD_ENV)
    assert rep.exit_code == EXIT_ENV


def test_wrong_message_type_is_an_interface_error():
    bad = stream(ticks(W0, W1, 25.0), "odom", msg_type="geometry_msgs/msg/PoseStamped")
    rep = run(healthy_observation(streams={"odom": bad}))
    assert rep.exit_code == EXIT_ENV
    assert any("odom" in r and "type" in r for r in rep.reasons)


def test_backward_clock_jump_is_reported_and_only_forward_progress_counts():
    first = clock_samples(W0, W0 + 2.0, 25.0, 0.4, sim0=500.0)
    second = clock_samples(W0 + 2.0, W1, 25.0, 0.4, sim0=0.0)  # timeline was reset to 0
    rep = run(healthy_observation(clock=tuple(first + second)))
    assert rep.exit_code == EXIT_HEALTHY
    assert rep.clock.backward_jumps == 1
    assert rep.clock.sim_progress_s == pytest.approx(0.8 + 1.2 - 2 * 0.016, abs=0.05)
    assert any("backward" in w for w in rep.warnings)


def test_stamp_lag_is_reported_against_the_latest_clock():
    lagging = stream(ticks(W0, W1, 25.0), "odom", sim_of=lambda t: default_sim(t) - 0.5)
    rep = run(healthy_observation(streams={"odom": lagging}))
    assert rep.streams["odom"].stamp_lag_s == pytest.approx(0.5, abs=0.05)


def test_report_serializes_to_plain_json_types():
    rep = run(healthy_observation())
    text = json.dumps(rep.to_dict())
    assert '"verdict": "healthy"' in text and '"exit_code": 0' in text


# ---- observation window bounds (review round 1: doctor_config-5) ---------------------------------------------------

@pytest.mark.parametrize("window,problem", [
    (0.0, "shorter than clock_stall_s"), (-5.0, "shorter than clock_stall_s"), (0.6, "shorter than clock_stall_s"),
    (float("nan"), "not a finite number"), (float("inf"), "not a finite number"), (True, "not a finite number"),
    (50.5, "longer than 50.0 s"), (100.0, "longer than 50.0 s"),
])
def test_window_that_cannot_give_a_sound_verdict_is_refused(window, problem):
    assert problem in window_problem(window, clock_stall_s=2.0, discovery_timeout_s=5.0)


@pytest.mark.parametrize("window", [2.0, 3.0, 5.0, 50.0])
def test_window_between_the_clock_stall_and_the_doctor_cap_is_accepted(window):
    assert window_problem(window, clock_stall_s=2.0, discovery_timeout_s=5.0) is None
