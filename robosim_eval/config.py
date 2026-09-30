"""Load configs/baseline.yaml into frozen dataclasses, with explicit validation errors.

Validation is strict so that a typo cannot silently change what a run tests: unknown keys, duplicate YAML keys, values
of the wrong type (a quoted number, a quoted boolean, null), non-finite numbers, unknown obstacle assets and duplicate
obstacle names are load errors. Every error is a ValueError whose one-line message names the key path; the doctor, the
runner and sim.sh turn it into exit 2.
"""
from __future__ import annotations

import math
import re
from collections.abc import Hashable
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union

import yaml

from robosim_eval.doctor_checks import DoctorThresholds, StreamThresholds, window_problem
from robosim_eval.nav2_params import node_and_param
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
    nav2_params: Mapping[str, Any] = field(default_factory=dict)  # D5: <node>.ros__parameters.<param> -> new scalar
    expect_safety: Optional[str] = None  # fault injection: the safety_status the scenario must produce (pass | fail)
    expect_data: Optional[str] = None    # fault injection: the data_status it must produce (complete | incomplete)


@dataclass(frozen=True)
class BaselineConfig:
    env: EnvExpect
    topics: Mapping[str, TopicSpec]
    doctor: DoctorConfig
    sim: Optional[SimConfig] = None
    run: Optional[RunConfig] = None
    scenarios: Mapping[str, Scenario] = field(default_factory=dict)


_TOP_KEYS = {"env", "topics", "doctor", "sim", "run", "scenarios"}
_ENV_KEYS = {"rmw", "domain_id", "ros_distro", "require_dds_profile"}
_TOPIC_KEYS = {"name", "type", "parent", "child"}
_DOCTOR_KEYS = {"discovery_timeout_s", "window_s", "clock_stall_s", "min_sim_progress_s", "streams"}
_STREAM_KEYS = {"min_rate_hz", "max_age_s"}
_SIM_KEYS = {"world_uri", "robot_entity", "spawn", "reset_check", "obstacle_usd", "obstacle_assets"}
_POSE_KEYS = {"x", "y", "yaw"}
_RESET_KEYS = {"position_m", "yaw_rad", "speed"}
_RUN_KEYS = {"frame", "units", "position_tolerance_m", "heading_assessed", "stop_still", "timeouts", "dropout_wall_s",
             "contact_filter", "contact", "streams", "record_cap_s"}
_STOP_KEYS = {"linear_mps", "angular_radps", "hold_sim_s", "max_gap_sim_s"}
_CONTACT_KEYS = {"robot_root", "ignore_prefixes"}
_RUN_STREAM_KEYS = {"required", "informational"}
_SCENARIO_KEYS = {"goal", "obstacles", "expect", "expect_outcome", "expect_safety", "expect_data", "preset_unreachable",
                  "evidence", "inject", "timeouts", "nav2_params"}
_OBSTACLE_KEYS = {"name", "x", "y", "yaw", "asset"}
_INJECT_KEYS = {"cancel_after_sim_s", "pause_after_sim_s", "pause_wall_s"}
_LIMIT_KEYS = {"ready_wall_s", "accept_wall_s", "nav_sim_s", "nav_wall_s", "cancel_wall_s", "stop_wall_s"}
_OUTCOMES = ("reached", "unreachable", "canceled", "timeout")   # A5 task outcomes a scenario may expect
_SAFETY = ("pass", "fail")
_DATA = ("complete", "incomplete")
_INTEGRITY_STREAMS = ("clock", "odom", "tf_odom_base", "tf_map_odom")   # scripts/wsl/analyze_attempt.py data_integrity
_DOMAIN_ID = re.compile(r"^(0|[1-9][0-9]{0,2})$")
_MAX_DOMAIN_ID = 232   # Fast DDS refuses larger domain ids
_DEFAULT_ASSET = Obstacle.asset


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys (plain PyYAML silently keeps the last one)."""


def _mapping_without_duplicates(loader: _StrictLoader, node: yaml.MappingNode) -> Dict[Any, Any]:
    seen = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue  # '<<' merges may be overridden on purpose
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, Hashable):
            continue  # construct_mapping below reports the unhashable key
        if key in seen:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark,
                                                    f"found duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep=True)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping_without_duplicates)


def _parse(path: Union[str, Path]) -> Any:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - a SafeLoader subclass
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        context = f" ({exc.context})" if exc.context else ""
        raise ValueError(f"{path}: invalid YAML{where}: {exc.problem}{context}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {' '.join(str(exc).split())}") from exc


def _brief(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _require(mapping: Mapping[str, Any], key: str, section: str) -> Any:
    if not isinstance(mapping, Mapping) or key not in mapping:
        raise ValueError(f"{section}.{key} is required")
    return mapping[key]


def _section(value: Any, where: str, allowed: Iterable[str], required: Sequence[str] = (),
             optional: bool = False) -> Mapping[str, Any]:
    """`value` as a mapping with only `allowed` keys and every `required` key; None is {} when `optional`."""
    if value is None and optional:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{where} must be a mapping, got {_brief(value)}")
    allowed = set(allowed)
    unknown = sorted(str(k) for k in value if k not in allowed)
    if unknown:
        raise ValueError(f"{where}: unknown key(s) {unknown} (allowed: {sorted(allowed)})")
    for key in required:
        if key not in value:
            raise ValueError(f"{where}.{key} is required")
    return value


def _entries(value: Any, where: str, optional: bool = True) -> Mapping[Any, Any]:
    """A mapping whose keys the config author names (topics, scenarios, assets); None is {} when `optional`."""
    if value is None and optional:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{where} must be a mapping, got {_brief(value)}")
    return value


def _number(where: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where} must be a number, got {_brief(value)}")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{where} is too large: {_brief(value)}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{where} must be a finite number, got {value!r}")
    return number


def _positive(section: str, key: str, value: Any) -> float:
    number = _number(f"{section}.{key}", value)
    if number <= 0:
        raise ValueError(f"{section}.{key} must be > 0, got {number}")
    return number


def _text(where: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where} must be a non-empty text, got {_brief(value)}")
    return value


def _optional_text(where: str, value: Any, default: Optional[str] = None) -> Optional[str]:
    return default if value is None else _text(where, value)


def _flag(where: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{where} must be true or false, got {_brief(value)}")
    return value


def _choice(where: str, value: Any, allowed: Sequence[str]) -> str:
    if value not in allowed or not isinstance(value, str):
        raise ValueError(f"{where}: {_brief(value)} is not one of {list(allowed)}")
    return value


def _pose(value: Any, where: str) -> Pose2D:
    p = _section(value, where, _POSE_KEYS, required=("x", "y", "yaw"))
    return Pose2D(_number(f"{where}.x", p["x"]), _number(f"{where}.y", p["y"]), _number(f"{where}.yaw", p["yaw"]))


def _domain_id(value: Any) -> str:
    text = str(value) if isinstance(value, int) and not isinstance(value, bool) else value
    if not isinstance(text, str) or not _DOMAIN_ID.match(text) or int(text) > _MAX_DOMAIN_ID:
        raise ValueError(f"env.domain_id must be a ROS domain id 0-{_MAX_DOMAIN_ID}, got {_brief(value)}")
    return text


def load_config(path: Union[str, Path]) -> BaselineConfig:
    """Read and validate the baseline configuration. Raises FileNotFoundError (OSError) or ValueError."""
    raw = _parse(path)
    raw = {} if raw is None else _section(raw, "config", _TOP_KEYS)
    env_raw = _section(_require(raw, "env", "config"), "env", _ENV_KEYS, required=("rmw", "domain_id", "ros_distro"))
    env = EnvExpect(rmw=_text("env.rmw", env_raw["rmw"]), domain_id=_domain_id(env_raw["domain_id"]),
                    ros_distro=_text("env.ros_distro", env_raw["ros_distro"]),
                    require_dds_profile=_flag("env.require_dds_profile", env_raw.get("require_dds_profile", True)))

    topics: Dict[str, TopicSpec] = {}
    for key, spec in _entries(_require(raw, "topics", "config"), "topics", optional=False).items():
        where = f"topics.{key}"
        s = _section(spec, where, _TOPIC_KEYS, required=("name", "type"))
        parent = _optional_text(f"{where}.parent", s.get("parent"))
        child = _optional_text(f"{where}.child", s.get("child"))
        if (parent is None) != (child is None):
            raise ValueError(f"{where}: parent and child must be given together (TF: count parent -> child)")
        topics[str(key)] = TopicSpec(name=_text(f"{where}.name", s["name"]), msg_type=_text(f"{where}.type", s["type"]),
                                     parent=parent, child=child)
    if "clock" not in topics:
        raise ValueError("topics.clock is required (the doctor judges simulation progress from it)")

    doc = _section(_require(raw, "doctor", "config"), "doctor", _DOCTOR_KEYS, required=("streams",))
    streams: Dict[str, StreamThresholds] = {}
    for key, th in _entries(doc["streams"], "doctor.streams", optional=False).items():
        if key not in topics:
            raise ValueError(f"doctor.streams.{key} has no entry under topics")
        s = _section(th, f"doctor.streams.{key}", _STREAM_KEYS)
        where = f"doctor.streams.{key}"
        streams[str(key)] = StreamThresholds(min_rate_hz=_positive(where, "min_rate_hz", s.get("min_rate_hz")),
                                             max_age_s=_positive(where, "max_age_s", s.get("max_age_s")))
    thresholds = DoctorThresholds(clock_stall_s=_positive("doctor", "clock_stall_s", doc.get("clock_stall_s")),
                                  min_sim_progress_s=_positive("doctor", "min_sim_progress_s",
                                                               doc.get("min_sim_progress_s")),
                                  streams=streams)
    doctor = DoctorConfig(discovery_timeout_s=_positive("doctor", "discovery_timeout_s",
                                                        doc.get("discovery_timeout_s")),
                          window_s=_positive("doctor", "window_s", doc.get("window_s")), thresholds=thresholds)
    problem = window_problem(doctor.window_s, thresholds.clock_stall_s, doctor.discovery_timeout_s)
    if problem:
        raise ValueError(f"doctor.window_s: {problem}")
    sim = _load_sim(raw.get("sim"))
    run, scenarios = _load_run(raw.get("run")), _load_scenarios(raw.get("scenarios"), sim)
    _check_record_cap(run, scenarios)
    return BaselineConfig(env=env, topics=topics, doctor=doctor, sim=sim, run=run, scenarios=scenarios)


# Wall time the runner still needs after the navigation and cancel/stop limits before it stops the recorders: settle
# (3 s), ground truth, contact fetch; generous, because a recording that ends early makes the run's data incomplete.
TEARDOWN_MARGIN_S = 30.0


def _check_record_cap(run: Optional[RunConfig], scenarios: Mapping[str, Scenario]) -> None:
    """The recorders are started with run.record_cap_s; it must cover the longest run of every scenario: acceptance,
    navigation (wall limit), an injected pause, cancel, stop confirmation and the teardown margin."""
    if run is None:
        return
    for name, sc in {"(run defaults)": None, **scenarios}.items():
        lim = dataclasses.replace(run.limits, **dict(sc.timeouts)) if sc else run.limits
        pause = float(sc.inject.get("pause_wall_s", 0.0)) if sc else 0.0
        need = lim.accept_wall_s + lim.nav_wall_s + pause + lim.cancel_wall_s + lim.stop_wall_s + TEARDOWN_MARGIN_S
        if run.record_cap_s < need:
            raise ValueError(f"run.record_cap_s {run.record_cap_s:g} s is shorter than the longest run of scenario "
                             f"{name!r}: {need:g} s (acceptance + navigation wall limit + pause + cancel + stop + "
                             f"{TEARDOWN_MARGIN_S:g} s teardown); the recorders would stop before the run is closed out")


def _stream_names(value: Any, where: str, default: Tuple[str, ...], allow_empty: bool) -> Tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{where} must be a list of stream names, got {_brief(value)}")
    unknown = [v for v in value if v not in _INTEGRITY_STREAMS]
    if unknown:
        raise ValueError(f"{where}: unknown stream(s) {unknown} (known: {list(_INTEGRITY_STREAMS)})")
    if not value and not allow_empty:
        raise ValueError(f"{where} must name at least one stream (with none, data could never be judged incomplete)")
    return tuple(value)


def _load_run(run: Any) -> Optional[RunConfig]:
    if run is None:
        return None
    r = _section(run, "run", _RUN_KEYS, required=("frame", "units", "heading_assessed", "stop_still", "timeouts",
                                                   "contact_filter"))
    stop = _section(r["stop_still"], "run.stop_still", _STOP_KEYS)
    t = _section(r["timeouts"], "run.timeouts", _LIMIT_KEYS)
    limits = Limits(**{k: _positive("run.timeouts", k, t.get(k)) for k in sorted(_LIMIT_KEYS)})
    units = {str(k): _text(f"run.units.{k}", v) for k, v in _entries(r["units"], "run.units", optional=False).items()}
    contact = _section(r.get("contact"), "run.contact", _CONTACT_KEYS, optional=True)
    prefixes = contact.get("ignore_prefixes")
    if prefixes is not None and (not isinstance(prefixes, list) or not all(isinstance(p, str) and p for p in prefixes)):
        raise ValueError(f"run.contact.ignore_prefixes must be a list of prim path prefixes, got {_brief(prefixes)}")
    streams = _section(r.get("streams"), "run.streams", _RUN_STREAM_KEYS, optional=True)
    return RunConfig(frame=_text("run.frame", r["frame"]), units=units,
                     position_tolerance_m=_positive("run", "position_tolerance_m", r.get("position_tolerance_m")),
                     heading_assessed=_flag("run.heading_assessed", r["heading_assessed"]),
                     stop_linear_mps=_positive("run.stop_still", "linear_mps", stop.get("linear_mps")),
                     stop_angular_radps=_positive("run.stop_still", "angular_radps", stop.get("angular_radps")),
                     stop_hold_sim_s=_positive("run.stop_still", "hold_sim_s", stop.get("hold_sim_s")),
                     stop_max_gap_sim_s=_positive("run.stop_still", "max_gap_sim_s", stop.get("max_gap_sim_s")),
                     limits=limits, dropout_wall_s=_positive("run", "dropout_wall_s", r.get("dropout_wall_s")),
                     contact_filter=_text("run.contact_filter", r["contact_filter"]),
                     record_cap_s=_positive("run", "record_cap_s", r.get("record_cap_s")),
                     contact_robot_root=_optional_text("run.contact.robot_root", contact.get("robot_root"),
                                                       "/World/Nova_Carter_ROS"),
                     contact_ignore_prefixes=tuple(prefixes or ()),
                     required_streams=_stream_names(streams.get("required"), "run.streams.required",
                                                    ("clock", "odom", "tf_odom_base"), allow_empty=False),
                     informational_streams=_stream_names(streams.get("informational"), "run.streams.informational",
                                                         ("tf_map_odom",), allow_empty=True))


def _obstacle_asset(where: str, value: Any, sim: Optional[SimConfig]) -> str:
    """The asset key an obstacle spawns from. A named asset must be a key of sim.obstacle_assets: an unknown name must
    not fall back to another obstacle (the low box of the collision scenario would silently become the 1 m box)."""
    assets = sim.obstacle_assets if sim is not None else {}
    if value is not None:
        asset = _text(f"{where}.asset", value)
        if asset not in assets:
            raise ValueError(f"{where}: asset {asset!r} is not a key of sim.obstacle_assets {sorted(assets)}")
        return asset
    if _DEFAULT_ASSET in assets or (sim is not None and sim.obstacle_usd):
        return _DEFAULT_ASSET
    raise ValueError(f"{where}: no asset given, and neither sim.obstacle_assets.{_DEFAULT_ASSET} nor sim.obstacle_usd "
                     "is configured")


def _load_obstacles(value: Any, where: str, sim: Optional[SimConfig]) -> Tuple[Obstacle, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{where}.obstacles must be a list, got {_brief(value)}")
    obstacles, seen = [], set()
    for i, ob_raw in enumerate(value):
        w = f"{where}.obstacles[{i}]"
        ob = _section(ob_raw, w, _OBSTACLE_KEYS, required=("name", "x", "y"))
        name = _text(f"{w}.name", ob["name"])
        try:
            full = validate_spawn_name(name)
        except ValueError as exc:
            raise ValueError(f"{w}.name: {exc}") from exc
        if full in seen:
            raise ValueError(f"{where}: duplicate obstacle name {name!r} (the second spawn would fail after the reset)")
        seen.add(full)
        obstacles.append(Obstacle(name=name, x=_number(f"{w}.x", ob["x"]), y=_number(f"{w}.y", ob["y"]),
                                  yaw=_number(f"{w}.yaw", ob.get("yaw", 0.0)),
                                  asset=_obstacle_asset(w, ob.get("asset"), sim)))
    return tuple(obstacles)


def _load_nav2_params(value: Any, where: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for key, v in _entries(value, f"{where}.nav2_params").items():
        w = f"{where}.nav2_params.{key}"
        try:
            node_and_param(_text(w, key))
        except ValueError as exc:
            raise ValueError(f"{w}: {exc}") from exc
        if not isinstance(v, (bool, int, float, str)):
            raise ValueError(f"{w}: need a scalar value, got {_brief(v)}")
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(f"{w} must be a finite number, got {v!r}")
        params[key] = v
    return params


def _load_scenarios(raw: Any, sim: Optional[SimConfig]) -> Dict[str, Scenario]:
    scenarios: Dict[str, Scenario] = {}
    for name, sc_raw in _entries(raw, "scenarios").items():
        where = f"scenarios.{name}"
        sc = _section(sc_raw, where, _SCENARIO_KEYS, required=("goal",))
        inject = _section(sc.get("inject"), f"{where}.inject", _INJECT_KEYS, optional=True)
        timeouts = _section(sc.get("timeouts"), f"{where}.timeouts", _LIMIT_KEYS, optional=True)
        safety, data = sc.get("expect_safety"), sc.get("expect_data")
        scenarios[str(name)] = Scenario(
            name=str(name), goal=_pose(sc["goal"], f"{where}.goal"),
            obstacles=_load_obstacles(sc.get("obstacles"), where, sim),
            expect=_optional_text(f"{where}.expect", sc.get("expect"), ""),
            expect_outcome=_choice(f"{where}.expect_outcome", sc.get("expect_outcome", "reached"), _OUTCOMES),
            preset_unreachable=_flag(f"{where}.preset_unreachable", sc.get("preset_unreachable", False)),
            evidence=_optional_text(f"{where}.evidence", sc.get("evidence"), ""),
            inject={str(k): _positive(f"{where}.inject", str(k), v) for k, v in inject.items()},
            timeouts={str(k): _positive(f"{where}.timeouts", str(k), v) for k, v in timeouts.items()},
            nav2_params=_load_nav2_params(sc.get("nav2_params"), where),
            expect_safety=None if safety is None else _choice(f"{where}.expect_safety", safety, _SAFETY),
            expect_data=None if data is None else _choice(f"{where}.expect_data", data, _DATA))
    return scenarios


def _load_sim(sim: Any) -> Optional[SimConfig]:
    if sim is None:
        return None
    s = _section(sim, "sim", _SIM_KEYS, required=("world_uri", "robot_entity", "spawn"))
    check = _section(s.get("reset_check"), "sim.reset_check", _RESET_KEYS, optional=True)
    assets = _entries(s.get("obstacle_assets"), "sim.obstacle_assets")
    return SimConfig(world_uri=_text("sim.world_uri", s["world_uri"]),
                     robot_entity=_text("sim.robot_entity", s["robot_entity"]),
                     spawn=_pose(s["spawn"], "sim.spawn"),
                     reset_position_m=_positive("sim.reset_check", "position_m", check.get("position_m", 0.05)),
                     reset_yaw_rad=_positive("sim.reset_check", "yaw_rad", check.get("yaw_rad", 0.05)),
                     reset_speed=_positive("sim.reset_check", "speed", check.get("speed", 0.02)),
                     obstacle_usd=_optional_text("sim.obstacle_usd", s.get("obstacle_usd")),
                     obstacle_assets={str(k): _text(f"sim.obstacle_assets.{k}", v) for k, v in assets.items()})
