"""ROS-free fakes for the runner tests (tests/test_runner_flow.py, tests/test_runner_prepare.py); no tests here.

A FakeWorld advances only when the runner spins or sleeps (fake monotonic time): /clock at rtf 0.4, odometry every
0.05 s wall (moving at 0.5 m/s while a goal is active), and a scripted NavigateToPose server (response delay, rejection,
lost response, finish time and status, honoured or ignored cancel, results by goal id).
"""
from __future__ import annotations

import argparse
import time as real_time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from robosim_eval import runner as runner_mod
from robosim_eval.config import load_config
from robosim_eval.run_io import EventLog
from robosim_eval.runner_fsm import RunStateMachine, State
from robosim_eval.sim_adapter import SimControlError

REPO = Path(__file__).resolve().parents[1]
FAKE_CFG = REPO / "tests" / "ros_fake" / "runner_fake.yaml"
PENDING = object()


class FakeFuture:
    def __init__(self, get: Callable[[], Any]) -> None:
        self._get = get

    def done(self) -> bool:
        return self._get() is not PENDING

    def result(self) -> Any:
        value = self._get()
        assert value is not PENDING, "result() of a pending future"
        return value


def terminal_response(status: int, error_code: int = 0) -> SimpleNamespace:
    return SimpleNamespace(status=status, result=SimpleNamespace(error_code=error_code, error_msg=""))


class FakeWorld:
    def __init__(self, response_delay: Optional[float] = 0.01, accept: bool = True, response_lost: bool = False,
                 finish_after: Optional[float] = None, finish_status: int = 4, cancel_honoured: bool = True,
                 moving_forever: bool = False, cancel_delay: float = 0.2) -> None:
        self.t, self.sim, self.rtf = 1000.0, 10.0, 0.4
        self.response_delay, self.accept, self.response_lost = response_delay, accept, response_lost
        self.finish_after, self.finish_status, self.cancel_honoured = finish_after, finish_status, cancel_honoured
        self.cancel_delay = cancel_delay
        self.moving_forever, self.paused = moving_forever, False
        self.sent_at: Optional[float] = None
        self.goal_uuid: Optional[bytes] = None
        self.cancel_at: Optional[float] = None
        self.terminal: Optional[SimpleNamespace] = None
        self.clock_msgs, self.odom, self._next_odom = 0, [], 1000.0
        self.cancel_requests = 0

    # time ---------------------------------------------------------------------------------------------------------
    def advance(self, dt: float) -> None:
        end = self.t + dt
        while self._next_odom <= end:
            step = self._next_odom - self.t
            self.t = self._next_odom
            if not self.paused:
                self.sim += step * self.rtf
                self.clock_msgs += 1
                self.odom.append((round(self.sim, 6), 0.5 if self.robot_moving() else 0.0, 0.0))
                del self.odom[:-400]
            self._next_odom += 0.05
            self._server_step()
        self.t = end
        self._server_step()

    # the action server --------------------------------------------------------------------------------------------
    def accepted_on_server(self) -> bool:
        return self.sent_at is not None and self.accept and self.response_delay is not None \
            and self.t >= self.sent_at + self.response_delay

    def robot_moving(self) -> bool:
        return self.moving_forever or (self.accepted_on_server() and self.terminal is None)

    def _server_step(self) -> None:
        if not self.accepted_on_server() or self.terminal is not None:
            return
        start = self.sent_at + self.response_delay
        if self.cancel_at is not None and self.cancel_honoured and self.t >= max(self.cancel_at, start) + self.cancel_delay:
            self.terminal = terminal_response(5)
        elif self.finish_after is not None and self.t >= start + self.finish_after:
            self.terminal = terminal_response(self.finish_status, 208 if self.finish_status == 6 else 0)

    def cancel(self) -> None:
        self.cancel_requests += 1
        if self.accepted_on_server() and self.cancel_at is None:
            self.cancel_at = self.t


class FakeHandle:
    def __init__(self, world: FakeWorld, accepted: bool) -> None:
        self.world, self.accepted = world, accepted
        self.goal_id = SimpleNamespace(uuid=list(world.goal_uuid))

    def cancel_goal_async(self) -> FakeFuture:
        self.world.cancel()
        return FakeFuture(lambda: SimpleNamespace(return_code=0))

    def get_result_async(self) -> FakeFuture:
        return FakeFuture(lambda: self.world.terminal if self.world.terminal is not None else PENDING)


class FakeNav:
    def __init__(self, world: FakeWorld) -> None:
        self.world, self.sent = world, []

    def server_is_ready(self) -> bool:
        return True

    def send_goal_async(self, goal, feedback_callback=None, goal_uuid=None) -> FakeFuture:
        w = self.world
        w.sent_at, w.goal_uuid = w.t, bytes(goal_uuid.uuid) if goal_uuid is not None else bytes(range(16))
        self.sent.append(goal)

        def response():
            if w.response_delay is None or w.response_lost or w.t < w.sent_at + w.response_delay:
                return PENDING
            return FakeHandle(w, w.accept)
        return FakeFuture(response)


def _goal() -> SimpleNamespace:
    ns = SimpleNamespace
    return ns(pose=ns(header=ns(frame_id=None), pose=ns(position=ns(x=0.0, y=0.0), orientation=ns(z=0.0, w=1.0))))


class FakeRunNode:
    """The RunNode interface the runner uses."""

    def __init__(self, world: FakeWorld) -> None:
        self.world, self.nav = world, FakeNav(world)
        self.clock_backward, self.feedback_count, self.last_feedback = 0, 0, {}
        self.NavigateToPose = SimpleNamespace(Goal=_goal)
        self.raw_cancels, self.list_calls = 0, 0
        self.entities: List[str] = []
        self.node = None
        self.rclpy = SimpleNamespace(spin_once=lambda node, timeout_sec: self.spin(timeout_sec))

    @property
    def sim_time(self) -> float:
        return self.world.sim

    @property
    def clock_msgs(self) -> int:
        return self.world.clock_msgs

    @property
    def odom(self) -> List[tuple]:
        return self.world.odom

    def spin(self, seconds: float = 0.05) -> None:
        self.world.advance(max(seconds, 0.0))

    def on_feedback(self, fb) -> None:
        self.feedback_count += 1

    def new_goal_uuid(self) -> SimpleNamespace:
        return SimpleNamespace(uuid=list(range(1, 17)))

    def cancel_by_id(self, uuid: bytes) -> FakeFuture:
        self.raw_cancels += 1
        self.world.cancel()
        return FakeFuture(lambda: SimpleNamespace(return_code=0))

    def result_by_id(self, uuid: bytes) -> FakeFuture:
        w = self.world
        if not w.accepted_on_server():
            return FakeFuture(lambda: terminal_response(0))   # STATUS_UNKNOWN: the server does not know the goal
        return FakeFuture(lambda: w.terminal if w.terminal is not None else PENDING)

    def list_entities(self, pattern: str) -> List[str]:
        self.list_calls += 1
        return list(self.entities)

    def lifecycle_active(self) -> List[str]:
        return []


class FakeSim:
    """SimAdapter stand-in: the robot's ground truth, simulation state, reset, load and spawn."""

    def __init__(self, world: FakeWorld, robot=(-6.0, -1.0, 3.141592653589793)) -> None:
        self.world, self.robot = world, robot
        self.state, self.calls = "playing", []
        self.fail: Dict[str, Exception] = {}          # method name -> exception to raise
        self.apply_then_fail: Dict[str, Exception] = {}  # set_state: apply the state, then raise (reply lost)
        self.entities: Dict[str, tuple] = {}

    def _maybe_fail(self, name: str) -> None:
        if name in self.fail:
            raise self.fail[name]

    def get_state(self) -> str:
        self.calls.append("get_state")
        self._maybe_fail("get_state")
        return self.state

    def set_state(self, name: str) -> str:
        self.calls.append(f"set_state({name})")
        self._maybe_fail("set_state")
        self.state = name
        self.world.paused = name == "paused"
        if name in self.apply_then_fail:
            raise self.apply_then_fail.pop(name)
        return name

    def entity_state(self, entity: str) -> Dict[str, Any]:
        self.calls.append(f"entity_state({entity})")
        self._maybe_fail("entity_state")
        x, y, yaw = self.entities.get(entity, self.robot)
        return {"entity": entity, "x": x, "y": y, "yaw": yaw, "linear_speed": 0.0, "angular_speed": 0.0}

    def reset(self) -> str:
        self.calls.append("reset")
        return "playing"

    def load_world(self, uri: str) -> str:
        self.calls.append(f"load_world({uri})")
        return "playing"

    def spawn_box(self, name: str, x: float, y: float, yaw: float, uri: str) -> str:
        self.calls.append(f"spawn_box({name})")
        full = f"/World/RoboSimObstacles/{name}"
        self.entities.setdefault(full, (x, y, yaw))
        return full


class FakeTime:
    """Replaces the runner module's `time`: monotonic time is the world's; sleep advances the world."""

    def __init__(self, world: FakeWorld) -> None:
        self.world = world

    def monotonic(self) -> float:
        return self.world.t

    def sleep(self, seconds: float) -> None:
        self.world.advance(seconds)

    def strftime(self, fmt: str) -> str:
        return real_time.strftime(fmt)


class Scripts:
    """Stand-in for runner.script: records calls, returns scripted exit codes, runs side effects (files)."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir, self.calls, self.codes, self.raises = run_dir, [], {}, {}
        # what the real start scripts leave behind (the runner treats these files as "started")
        self.effects: Dict[str, Callable[[Path], Any]] = {
            "record_d0.sh": lambda d: (d / "record.pids").write_text("bag 4242\n"),
            "start_nav2.sh": lambda d: (d / "nav2.pid").write_text("4343\n")}

    def __call__(self, name: str, args: List[str], log: Path, timeout: float) -> int:
        self.calls.append((name, list(args)))
        if name in self.raises:
            raise self.raises[name]
        if name in self.effects:
            self.effects[name](self.run_dir)
        return self.codes.get(name, 0)

    def names(self) -> List[str]:
        return [c[0] for c in self.calls]


def options(**kw) -> argparse.Namespace:
    base = dict(config=str(FAKE_CFG), no_sim=True, no_nav2=True, no_record=True, no_analyze=True, no_contacts=True,
                test_fault=None)
    base.update(kw)
    return argparse.Namespace(**base)


def make_runner(tmp_path: Path, monkeypatch, world: Optional[FakeWorld] = None, cfg_path: Path = FAKE_CFG,
                scenario: str = "fake", **opts):
    """A Runner wired to the fakes, in PREPARE, with its own run dir; returns (runner, world, scripts)."""
    world = world or FakeWorld()
    cfg = load_config(cfg_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(runner_mod, "time", FakeTime(world))
    scripts = Scripts(run_dir)
    monkeypatch.setattr(runner_mod, "script", scripts)
    r = runner_mod.Runner(cfg, cfg.scenarios[scenario], run_dir, options(config=str(cfg_path), **opts))
    r.rn, r.sim = FakeRunNode(world), FakeSim(world)
    r.ev = EventLog(run_dir / "events.jsonl", lambda: r.rn.sim_time)
    r.fsm = RunStateMachine(r.limits, world.t, None)
    r._logged = 0
    return r, world, scripts


SIM_SECTION = """
sim:
  world_uri: https://example.invalid/Isaac/6.1/world.usd
  robot_entity: /World/Nova_Carter_ROS/chassis_link
  spawn: {x: -6.0, y: -1.0, yaw: 3.141592653589793}
  obstacle_usd: D:/RoboSim-Eval/configs/assets/box_1m.usda
  obstacle_assets: {box_1m: D:/RoboSim-Eval/configs/assets/box_1m.usda}
"""
SIM_SCENARIOS = """scenarios:
  fake:
    goal: {x: 1.0, y: 0.0, yaw: 0.0}
    expect: "fake"
  pause:
    goal: {x: 1.0, y: 0.0, yaw: 0.0}
    inject: {pause_after_sim_s: 0.5, pause_wall_s: 6.0}
    expect: "fake"
  box:
    goal: {x: 0.0, y: -1.0, yaw: 0.0}
    obstacles: [{name: box_1, x: -3.0, y: -1.3, yaw: 0.0, asset: box_1m}]
    expect: "fake"
  unreachable:
    goal: {x: -10.05, y: -1.0, yaw: 3.141592653589793}
    expect_outcome: unreachable
    preset_unreachable: true
    evidence: "test"
    expect: "fake"
"""


def sim_config(tmp_path: Path) -> Path:
    """runner_fake.yaml with a sim section and scenarios for the simulator-side paths."""
    base = FAKE_CFG.read_text(encoding="utf-8").split("scenarios:")[0]
    p = tmp_path / "runner_sim.yaml"
    p.write_text(base + SIM_SECTION + SIM_SCENARIOS, encoding="utf-8")
    return p


def to_send_goal(r) -> None:
    r.fsm.go(State.WAIT_READY, r.rn.world.t, r.rn.sim_time, "prepared")
    r.fsm.go(State.SEND_GOAL, r.rn.world.t, r.rn.sim_time, "nav2 ready")


def events(r) -> List[Dict[str, Any]]:
    import json
    return [json.loads(line) for line in (r.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def drive(r, *steps: Callable[[], bool]) -> None:
    """The step chain of Runner.run() with its handler: any exception becomes an internal error (then teardown)."""
    try:
        for step in steps:
            if not step():
                break
    except Exception as exc:  # noqa: BLE001 - mirrors Runner.run()
        r.fsm.fail(f"internal error: {type(exc).__name__}: {exc}", *r.now())


def finish(r):
    """Teardown and result, as Runner.run() ends; returns (exit code, result.json)."""
    import json
    r._sync()
    r._teardown()
    return r._exit_code(), json.loads((r.run_dir / "result.json").read_text(encoding="utf-8"))


__all__ = ["FakeWorld", "FakeSim", "FakeRunNode", "Scripts", "SimControlError", "make_runner", "to_send_goal",
           "events", "options", "sim_config", "drive", "finish", "FAKE_CFG", "REPO"]
