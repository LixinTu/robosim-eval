"""Load configs/baseline.yaml into frozen dataclasses, with explicit validation errors."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, Union

import yaml

from robosim_eval.doctor_checks import DoctorThresholds, StreamThresholds
from robosim_eval.runner_fsm import Limits
from robosim_eval.sim_math import Pose2D, validate_spawn_name

__all__ = ["EnvExpect", "TopicSpec", "DoctorConfig", "SimConfig", "RunConfig", "Obstacle", "Scenario",
           "BaselineConfig", "load_config"]


@dataclass(frozen=True)
class EnvExpect:
    rmw: str
    domain_id: str
    ros_distro: str
    require_dds_profile: bool


@dataclass(frozen=True)
class TopicSpec:
    name: str
    msg_type: str
    parent: Optional[str] = None  # TF only: count transforms parent -> child
    child: Optional[str] = None


@dataclass(frozen=True)
class DoctorConfig:
    discovery_timeout_s: float
    window_s: float
    thresholds: DoctorThresholds


@dataclass(frozen=True)
class SimConfig:
    world_uri: str
    robot_entity: str
    spawn: Pose2D
    reset_position_m: float
    reset_yaw_rad: float
    reset_speed: float
    obstacle_usd: Optional[str] = None
    obstacle_assets: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunConfig:
    frame: str
    units: Mapping[str, str]
    position_tolerance_m: float
    heading_assessed: bool
    stop_linear_mps: float
    stop_angular_radps: float
    stop_hold_sim_s: float
    stop_max_gap_sim_s: float
    limits: Limits
    dropout_wall_s: float
    contact_filter: str
    record_cap_s: float
    contact_robot_root: str = "/World/Nova_Carter_ROS"
    contact_ignore_prefixes: Tuple[str, ...] = ()
    required_streams: Tuple[str, ...] = ("clock", "odom", "tf_odom_base")
    informational_streams: Tuple[str, ...] = ("tf_map_odom",)


@dataclass(frozen=True)
class Obstacle:
    name: str
    x: float
    y: float
    yaw: float = 0.0
    asset: str = "box_1m"


@dataclass(frozen=True)
class Scenario:
    name: str
    goal: Pose2D
    obstacles: Tuple[Obstacle, ...]
    expect: str
    expect_outcome: str = "reached"
    preset_unreachable: bool = False
    evidence: str = ""
    inject: Mapping[str, float] = field(default_factory=dict)
    timeouts: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BaselineConfig:
    env: EnvExpect
    topics: Mapping[str, TopicSpec]
    doctor: DoctorConfig
    sim: Optional[SimConfig] = None
    run: Optional[RunConfig] = None
    scenarios: Mapping[str, Scenario] = field(default_factory=dict)


def _positive(section: str, key: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{section}.{key} must be a number, got {value!r}") from exc
    if number <= 0:
        raise ValueError(f"{section}.{key} must be > 0, got {number}")
    return number


def _require(mapping: Mapping[str, Any], key: str, section: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise ValueError(f"{section}.{key} is required")
    return mapping[key]


def load_config(path: Union[str, Path]) -> BaselineConfig:
    """Read and validate the baseline configuration. Raises FileNotFoundError or ValueError."""
    raw: Dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    env_raw = _require(raw, "env", "config")
    env = EnvExpect(rmw=str(_require(env_raw, "rmw", "env")), domain_id=str(_require(env_raw, "domain_id", "env")),
                    ros_distro=str(_require(env_raw, "ros_distro", "env")),
                    require_dds_profile=bool(env_raw.get("require_dds_profile", True)))

    topics_raw = _require(raw, "topics", "config")
    topics: Dict[str, TopicSpec] = {}
    for key, spec in topics_raw.items():
        topics[key] = TopicSpec(name=str(_require(spec, "name", f"topics.{key}")),
                                msg_type=str(_require(spec, "type", f"topics.{key}")),
                                parent=spec.get("parent"), child=spec.get("child"))
    if "clock" not in topics:
        raise ValueError("topics.clock is required (the doctor judges simulation progress from it)")

    doc = _require(raw, "doctor", "config")
    streams_raw = _require(doc, "streams", "doctor")
    streams: Dict[str, StreamThresholds] = {}
    for key, th in streams_raw.items():
        if key not in topics:
            raise ValueError(f"doctor.streams.{key} has no entry under topics")
        streams[key] = StreamThresholds(min_rate_hz=_positive(f"doctor.streams.{key}", "min_rate_hz", th.get("min_rate_hz")),
                                        max_age_s=_positive(f"doctor.streams.{key}", "max_age_s", th.get("max_age_s")))
    thresholds = DoctorThresholds(clock_stall_s=_positive("doctor", "clock_stall_s", doc.get("clock_stall_s")),
                                  min_sim_progress_s=_positive("doctor", "min_sim_progress_s",
                                                               doc.get("min_sim_progress_s")),
                                  streams=streams)
    doctor = DoctorConfig(discovery_timeout_s=_positive("doctor", "discovery_timeout_s", doc.get("discovery_timeout_s")),
                          window_s=_positive("doctor", "window_s", doc.get("window_s")), thresholds=thresholds)
    return BaselineConfig(env=env, topics=topics, doctor=doctor, sim=_load_sim(raw.get("sim")),
                          run=_load_run(raw.get("run")), scenarios=_load_scenarios(raw.get("scenarios")))


def _load_run(run: Optional[Mapping[str, Any]]) -> Optional[RunConfig]:
    if run is None:
        return None
    stop = _require(run, "stop_still", "run")
    t = _require(run, "timeouts", "run")
    limits = Limits(**{k: _positive("run.timeouts", k, t.get(k)) for k in
                       ("ready_wall_s", "accept_wall_s", "nav_sim_s", "nav_wall_s", "cancel_wall_s", "stop_wall_s")})
    return RunConfig(frame=str(_require(run, "frame", "run")), units=dict(_require(run, "units", "run")),
                     position_tolerance_m=_positive("run", "position_tolerance_m", run.get("position_tolerance_m")),
                     heading_assessed=bool(_require(run, "heading_assessed", "run")),
                     stop_linear_mps=_positive("run.stop_still", "linear_mps", stop.get("linear_mps")),
                     stop_angular_radps=_positive("run.stop_still", "angular_radps", stop.get("angular_radps")),
                     stop_hold_sim_s=_positive("run.stop_still", "hold_sim_s", stop.get("hold_sim_s")),
                     stop_max_gap_sim_s=_positive("run.stop_still", "max_gap_sim_s", stop.get("max_gap_sim_s")),
                     limits=limits, dropout_wall_s=_positive("run", "dropout_wall_s", run.get("dropout_wall_s")),
                     contact_filter=str(_require(run, "contact_filter", "run")),
                     record_cap_s=_positive("run", "record_cap_s", run.get("record_cap_s")),
                     contact_robot_root=str((run.get("contact") or {}).get("robot_root", "/World/Nova_Carter_ROS")),
                     contact_ignore_prefixes=tuple((run.get("contact") or {}).get("ignore_prefixes") or ()),
                     required_streams=tuple((run.get("streams") or {}).get("required", ("clock", "odom", "tf_odom_base"))),
                     informational_streams=tuple((run.get("streams") or {}).get("informational", ("tf_map_odom",))))


_INJECT_KEYS = {"cancel_after_sim_s", "pause_after_sim_s", "pause_wall_s"}
_LIMIT_KEYS = {"ready_wall_s", "accept_wall_s", "nav_sim_s", "nav_wall_s", "cancel_wall_s", "stop_wall_s"}


def _load_scenarios(raw: Optional[Mapping[str, Any]]) -> Dict[str, Scenario]:
    scenarios: Dict[str, Scenario] = {}
    for name, sc in (raw or {}).items():
        goal = _require(sc, "goal", f"scenarios.{name}")
        obstacles = []
        for i, ob in enumerate(sc.get("obstacles") or []):
            validate_spawn_name(str(_require(ob, "name", f"scenarios.{name}.obstacles[{i}]")))  # raises outside the root
            obstacles.append(Obstacle(name=str(ob["name"]), x=float(_require(ob, "x", f"scenarios.{name}.obstacles[{i}]")),
                                      y=float(_require(ob, "y", f"scenarios.{name}.obstacles[{i}]")),
                                      yaw=float(ob.get("yaw", 0.0)), asset=str(ob.get("asset", "box_1m"))))
        inject = {str(k): _positive(f"scenarios.{name}.inject", str(k), v) for k, v in (sc.get("inject") or {}).items()}
        unknown = set(inject) - _INJECT_KEYS
        if unknown:
            raise ValueError(f"scenarios.{name}.inject: unknown key(s) {sorted(unknown)} (allowed {sorted(_INJECT_KEYS)})")
        timeouts = {str(k): _positive(f"scenarios.{name}.timeouts", str(k), v) for k, v in (sc.get("timeouts") or {}).items()}
        if set(timeouts) - _LIMIT_KEYS:
            raise ValueError(f"scenarios.{name}.timeouts: unknown key(s) {sorted(set(timeouts) - _LIMIT_KEYS)}")
        expect_outcome = str(sc.get("expect_outcome", "reached"))
        if expect_outcome not in ("reached", "unreachable", "canceled", "timeout"):
            raise ValueError(f"scenarios.{name}.expect_outcome: {expect_outcome!r} is not an A5 task outcome")
        scenarios[name] = Scenario(name=name, goal=Pose2D(float(_require(goal, "x", f"scenarios.{name}.goal")),
                                                          float(_require(goal, "y", f"scenarios.{name}.goal")),
                                                          float(_require(goal, "yaw", f"scenarios.{name}.goal"))),
                                   obstacles=tuple(obstacles), expect=str(sc.get("expect", "")),
                                   expect_outcome=expect_outcome, preset_unreachable=bool(sc.get("preset_unreachable", False)),
                                   evidence=str(sc.get("evidence", "")), inject=inject, timeouts=timeouts)
    return scenarios


def _load_sim(sim: Optional[Mapping[str, Any]]) -> Optional[SimConfig]:
    if sim is None:
        return None
    spawn = _require(sim, "spawn", "sim")
    check = sim.get("reset_check", {})
    return SimConfig(world_uri=str(_require(sim, "world_uri", "sim")),
                     robot_entity=str(_require(sim, "robot_entity", "sim")),
                     spawn=Pose2D(float(_require(spawn, "x", "sim.spawn")), float(_require(spawn, "y", "sim.spawn")),
                                  float(_require(spawn, "yaw", "sim.spawn"))),
                     reset_position_m=_positive("sim.reset_check", "position_m", check.get("position_m", 0.05)),
                     reset_yaw_rad=_positive("sim.reset_check", "yaw_rad", check.get("yaw_rad", 0.05)),
                     reset_speed=_positive("sim.reset_check", "speed", check.get("speed", 0.02)),
                     obstacle_usd=sim.get("obstacle_usd"),
                     obstacle_assets={str(k): str(v) for k, v in (sim.get("obstacle_assets") or {}).items()})
