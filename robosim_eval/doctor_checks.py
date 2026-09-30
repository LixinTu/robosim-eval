"""Pure verdict logic for the D1 doctor: clock progress, stream rates and freshness -> verdict and exit code.

No ROS imports here, so every rule is testable with fixed inputs (tests/test_doctor_checks.py).
Time bases: receive times are wall-clock seconds (monotonic); header stamps and /clock values are simulation seconds.

Verdict precedence (first match wins):
  13 env_or_interface_error  RMW / domain / DDS profile / ROS distro differ from the expected values, or a publisher
                             of a configured topic has another message type than configured (types are taken from the
                             publishers, never from the doctor's own subscriptions in the ROS graph)
  11 sim_data_missing        /clock has no publisher (Isaac closed, bridge not loaded, or DDS discovery broken)
  10 sim_not_advancing       /clock has a publisher but did not advance: no messages, frozen value, or it stalled for
                             longer than clock_stall_s before the window ended (typically: simulation paused/stopped)
  11 sim_data_missing        the clock advances but a required stream has no publisher
  12 degraded                a required stream is silent, stale (last message older than max_age_s) or slower than
                             min_rate_hz
   0 healthy
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

EXIT_HEALTHY = 0
EXIT_NOT_ADVANCING = 10
EXIT_DATA_MISSING = 11
EXIT_DEGRADED = 12
EXIT_ENV = 13

DOCTOR_SH_CAP_S = 60.0        # scripts/wsl/doctor.sh runs the doctor under `timeout 60`
START_STOP_ALLOWANCE_S = 5.0  # Python/rclpy start-up and shutdown (about 3 s measured) plus margin

Sample = Tuple[float, Optional[float]]  # (receive time, wall s; header stamp, sim s or None)


def window_problem(window_s: Any, clock_stall_s: float, discovery_timeout_s: float) -> Optional[str]:
    """Why an observation window (wall s) cannot give a sound verdict, or None when it can.

    The window must be finite and at least clock_stall_s: a shorter one can never see a stall, and min_sim_progress_s is
    not scaled with the window, so at the measured real-time factor of about 0.32 a 0.6 s window reports a healthy
    simulation as not advancing. It must also be short enough that discovery, the window and start-up stay under the
    60 s cap of doctor.sh, which would otherwise end the run as a hang (124)."""
    if isinstance(window_s, bool) or not isinstance(window_s, (int, float)) or not math.isfinite(window_s):
        return f"window {window_s!r} s is not a finite number"
    if window_s < clock_stall_s:
        return f"window {window_s} s is shorter than clock_stall_s ({clock_stall_s} s)"
    longest = DOCTOR_SH_CAP_S - discovery_timeout_s - START_STOP_ALLOWANCE_S
    if window_s > longest:
        return (f"window {window_s} s is longer than {longest} s (doctor.sh cap {DOCTOR_SH_CAP_S:.0f} s minus "
                f"discovery_timeout_s and {START_STOP_ALLOWANCE_S:.0f} s start-up)")
    return None


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
    msg_types: Tuple[str, ...]  # message types of the topic's publishers; empty without a publisher
    samples: Sequence[Sample]


@dataclass(frozen=True)
class Observation:
    window_start: float
    window_end: float
    clock_present: bool
    clock_types: Tuple[str, ...]  # message types of the /clock publishers
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
    msg_types: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StreamStats:
    present: bool
    msg_types: Tuple[str, ...]
    count: int
    rate_hz: float
    max_gap_s: Optional[float]
    last_age_s: Optional[float]
    stamp_lag_s: Optional[float]
    status: str  # ok | missing | silent | stale | slow | not_observed
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
    observed: bool = True  # False: judged from the environment alone, the ROS graph was not looked at

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
        msg_types=tuple(obs.clock_types),
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
    return StreamStats(present=so.present, msg_types=tuple(so.msg_types), count=count, rate_hz=rate, max_gap_s=max_gap,
                       last_age_s=last_age, stamp_lag_s=lag, status=status, detail=detail)


def env_reasons(env: EnvFacts, expected: EnvFacts) -> List[str]:
    """Differences between the current environment and the expected one (13 when non-empty)."""
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
        so = obs.streams.get(name, StreamObservation(present=False, msg_types=(), samples=()))
        streams[name] = _stream_stats(name, so, th, obs.window_end, window, clock.last_sim_s)

    problems = env_reasons(obs.env, expected_env)
    for name, published in [("clock", obs.clock_types)] + [(n, st.msg_types) for n, st in streams.items()]:
        want = expected_types.get(name)
        wrong = [t for t in published if want and t != want]
        if wrong:  # one wrong publisher is enough: its messages never reach the doctor's subscription
            problems.append(f"{name}: publisher message type {', '.join(wrong)} != expected {want}")

    def report(verdict: str, code: int, reasons: List[str]) -> DoctorReport:
        return DoctorReport(verdict=verdict, exit_code=code, reasons=tuple(reasons), warnings=tuple(warnings),
                            window_s=window, clock=clock, streams=streams)

    if problems:
        return report("env_or_interface_error", EXIT_ENV, problems)
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


def not_observed_report(reasons: Sequence[str], thresholds: DoctorThresholds) -> DoctorReport:
    """Exit 13 judged from the environment alone, before any ROS use: observing with a wrong RMW, domain or profile
    would be meaningless, and an RMW library that cannot be loaded makes rcl end the process on import."""
    clock = ClockStats(present=False, count=0, rate_hz=0.0, sim_progress_s=0.0, rtf=None, last_age_s=None,
                       backward_jumps=0, last_sim_s=None)
    streams = {name: StreamStats(present=False, msg_types=(), count=0, rate_hz=0.0, max_gap_s=None, last_age_s=None,
                                 stamp_lag_s=None, status="not_observed", detail=f"{name}: not observed")
               for name in thresholds.streams}
    return DoctorReport(verdict="env_or_interface_error", exit_code=EXIT_ENV, reasons=tuple(reasons), warnings=(),
                        window_s=0.0, clock=clock, streams=streams, observed=False)
