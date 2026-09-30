"""Load configs/baseline.yaml into frozen dataclasses, with explicit validation errors."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

import yaml

from robosim_eval.doctor_checks import DoctorThresholds, StreamThresholds
from robosim_eval.sim_math import Pose2D

__all__ = ["EnvExpect", "TopicSpec", "DoctorConfig", "SimConfig", "BaselineConfig", "load_config"]


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


@dataclass(frozen=True)
class BaselineConfig:
    env: EnvExpect
    topics: Mapping[str, TopicSpec]
    doctor: DoctorConfig
    sim: Optional[SimConfig] = None


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
    return BaselineConfig(env=env, topics=topics, doctor=doctor, sim=_load_sim(raw.get("sim")))


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
                     obstacle_usd=sim.get("obstacle_usd"))
