"""Pure verdict logic for the D1 doctor: clock progress, stream rates and freshness -> verdict and exit code.

No ROS imports here, so every rule is testable with fixed inputs (tests/test_doctor_checks.py).
Time bases: receive times are wall-clock seconds (monotonic); header stamps and /clock values are simulation seconds.

Verdict precedence (first match wins):
  13 env_or_interface_error  RMW / domain / DDS profile / ROS distro differ from the expected values, or a topic has
                             an unexpected message type
  11 sim_data_missing        /clock has no publisher (Isaac closed, bridge not loaded, or DDS discovery broken)
  10 sim_not_advancing       /clock has a publisher but did not advance: no messages, frozen value, or it stalled for
                             longer than clock_stall_s before the window ended (typically: simulation paused/stopped)
  11 sim_data_missing        the clock advances but a required stream has no publisher
  12 degraded                a required stream is silent, stale (last message older than max_age_s) or slower than
                             min_rate_hz
   0 healthy
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

EXIT_HEALTHY = 0
EXIT_NOT_ADVANCING = 10
EXIT_DATA_MISSING = 11
EXIT_DEGRADED = 12
EXIT_ENV = 13

Sample = Tuple[float, Optional[float]]  # (receive time, wall s; header stamp, sim s or None)


@dataclass(frozen=True)
class StreamThresholds:
    min_rate_hz: float
    max_age_s: float


@dataclass(frozen=True)
class DoctorThresholds:
    clock_stall_s: float
    min_sim_progress_s: float
    streams: Mapping[str, StreamThresholds]


@dataclass(frozen=True)
class EnvFacts:
    rmw: Optional[str]
    domain_id: Optional[str]
    dds_profile_exists: bool
    ros_distro: Optional[str]


@dataclass(frozen=True)
class StreamObservation:
    present: bool
    msg_type: Optional[str]
    samples: Sequence[Sample]


@dataclass(frozen=True)
class Observation:
    window_start: float
    window_end: float
    clock_present: bool
    clock_type: Optional[str]
    clock: Sequence[Tuple[float, float]]
    streams: Mapping[str, StreamObservation]
    env: EnvFacts


@dataclass(frozen=True)
class ClockStats:
    present: bool
    count: int
    rate_hz: float
    sim_progress_s: float
    rtf: Optional[float]
    last_age_s: Optional[float]
    backward_jumps: int
    last_sim_s: Optional[float]


@dataclass(frozen=True)
class StreamStats:
    present: bool
    msg_type: Optional[str]
    count: int
    rate_hz: float
    max_gap_s: Optional[float]
    last_age_s: Optional[float]
    stamp_lag_s: Optional[float]
    status: str  # ok | missing | silent | stale | slow
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    verdict: str
    exit_code: int
    reasons: Tuple[str, ...]
    warnings: Tuple[str, ...]
    window_s: float
    clock: ClockStats
    streams: Mapping[str, StreamStats]

    def to_dict(self) -> dict:
        """Plain JSON-serializable dict (nested dataclasses become dicts, tuples become lists)."""
        return asdict(self)


def _clock_stats(obs: Observation, window: float) -> Tuple[ClockStats, List[str]]:
    samples = list(obs.clock)
    progress, backward = 0.0, 0
    for (_, a), (_, b) in zip(samples, samples[1:]):
        if b > a:
            progress += b - a
        elif b < a:
            backward += 1
    warnings = [f"/clock jumped backward {backward} time(s) in the window (timeline reset or stop/play)"] if backward else []
    span = samples[-1][0] - samples[0][0] if len(samples) >= 2 else 0.0
    stats = ClockStats(
        present=obs.clock_present,
        count=len(samples),
        rate_hz=len(samples) / window,
        sim_progress_s=progress,
        rtf=(progress / span) if span > 0 else None,
        last_age_s=(obs.window_end - samples[-1][0]) if samples else None,
        backward_jumps=backward,
        last_sim_s=samples[-1][1] if samples else None,
    )
    return stats, warnings


def _stream_stats(name: str, so: StreamObservation, th: StreamThresholds, window_end: float, window: float,
                  clock_sim: Optional[float]) -> StreamStats:
    times = [s[0] for s in so.samples]
    count = len(times)
    rate = count / window
    max_gap = max((b - a for a, b in zip(times, times[1:])), default=None)
    last_age = (window_end - times[-1]) if times else None
    last_stamp = so.samples[-1][1] if so.samples else None
    lag = (clock_sim - last_stamp) if (clock_sim is not None and last_stamp is not None) else None
    if not so.present:
        status, detail = "missing", f"{name}: no publisher for the topic"
    elif count == 0:
        status, detail = "silent", f"{name}: publisher present but no message in {window:.1f} s"
    elif last_age is not None and last_age > th.max_age_s:
        status, detail = "stale", f"{name}: last message {last_age:.2f} s old > {th.max_age_s} s"
    elif rate < th.min_rate_hz:
        status, detail = "slow", f"{name}: {rate:.2f} Hz < {th.min_rate_hz} Hz"
    else:
        status, detail = "ok", f"{name}: {rate:.2f} Hz, last message {last_age:.2f} s old"
    return StreamStats(present=so.present, msg_type=so.msg_type, count=count, rate_hz=rate, max_gap_s=max_gap,
                       last_age_s=last_age, stamp_lag_s=lag, status=status, detail=detail)


def _env_reasons(env: EnvFacts, expected: EnvFacts) -> List[str]:
    reasons = []
    if expected.rmw and env.rmw != expected.rmw:
        reasons.append(f"RMW_IMPLEMENTATION is {env.rmw!r}, expected {expected.rmw!r}")
    if expected.domain_id is not None and env.domain_id != expected.domain_id:
        reasons.append(f"ROS_DOMAIN_ID is {env.domain_id!r}, expected {expected.domain_id!r}")
    if expected.dds_profile_exists and not env.dds_profile_exists:
        reasons.append("Fast DDS profile (FASTRTPS_DEFAULT_PROFILES_FILE) is not set or the file does not exist")
    if expected.ros_distro and env.ros_distro != expected.ros_distro:
        reasons.append(f"ROS_DISTRO is {env.ros_distro!r}, expected {expected.ros_distro!r}")
    return reasons


def evaluate(obs: Observation, thresholds: DoctorThresholds, expected_types: Mapping[str, str],
             expected_env: EnvFacts) -> DoctorReport:
    """Turn one bounded observation into a verdict; see the module docstring for the precedence."""
    window = max(obs.window_end - obs.window_start, 1e-9)
    clock, warnings = _clock_stats(obs, window)
    streams: Dict[str, StreamStats] = {}
    for name, th in thresholds.streams.items():
        so = obs.streams.get(name, StreamObservation(present=False, msg_type=None, samples=()))
        streams[name] = _stream_stats(name, so, th, obs.window_end, window, clock.last_sim_s)

    env_reasons = _env_reasons(obs.env, expected_env)
    if obs.clock_present and obs.clock_type and obs.clock_type != expected_types.get("clock", obs.clock_type):
        env_reasons.append(f"clock: message type {obs.clock_type} != expected {expected_types['clock']}")
    for name, st in streams.items():
        want = expected_types.get(name)
        if st.present and st.msg_type and want and st.msg_type != want:
            env_reasons.append(f"{name}: message type {st.msg_type} != expected {want}")

    def report(verdict: str, code: int, reasons: List[str]) -> DoctorReport:
        return DoctorReport(verdict=verdict, exit_code=code, reasons=tuple(reasons), warnings=tuple(warnings),
                            window_s=window, clock=clock, streams=streams)

    if env_reasons:
        return report("env_or_interface_error", EXIT_ENV, env_reasons)
    if not obs.clock_present:
        return report("sim_data_missing", EXIT_DATA_MISSING,
                      ["clock: no publisher for /clock (Isaac Sim closed, ROS 2 bridge not loaded, or DDS discovery "
                       "broken)"])
    if clock.count == 0:
        return report("sim_not_advancing", EXIT_NOT_ADVANCING,
                      [f"clock: publisher present but no /clock message in {window:.1f} s (simulation paused or stopped)"])
    if clock.sim_progress_s < thresholds.min_sim_progress_s:
        return report("sim_not_advancing", EXIT_NOT_ADVANCING,
                      [f"clock: simulation time advanced only {clock.sim_progress_s:.3f} s in {window:.1f} s "
                       f"(< {thresholds.min_sim_progress_s} s)"])
    if clock.last_age_s is not None and clock.last_age_s > thresholds.clock_stall_s:
        return report("sim_not_advancing", EXIT_NOT_ADVANCING,
                      [f"clock: last /clock message {clock.last_age_s:.2f} s before the end of the window "
                       f"(> {thresholds.clock_stall_s} s; simulation paused during the check)"])
    missing = [st.detail for st in streams.values() if st.status == "missing"]
    if missing:
        return report("sim_data_missing", EXIT_DATA_MISSING, missing)
    degraded = [st.detail for st in streams.values() if st.status != "ok"]
    if degraded:
        return report("degraded", EXIT_DEGRADED, degraded)
    return report("healthy", EXIT_HEALTHY, [])
