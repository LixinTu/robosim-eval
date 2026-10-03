"""D2 single-run runner: one config-driven A->B navigation with a timeout-guarded state machine and a full teardown.

Run in WSL through scripts/wsl/run_scenario.sh (it sources the ROS and Fast DDS environment):
  python3 -m robosim_eval.runner --scenario normal [--config configs/baseline.yaml] [--out artifacts/d2/runs]
         [--no-sim] [--no-nav2] [--no-record] [--no-analyze] [--no-contacts] [--test-fault executing]
One runner per ROS domain at a time: an exclusive lock (run_io.runner_lock_path, owner pid and run dir inside) is taken
before PREPARE, so a second runner never resets the simulation or drains the contact buffer of a running one.
Steps (robosim_eval.runner_fsm): PREPARE (manifest, resolved config, start/goal map check, sim reset + reset-check,
obstacles read back, doctor) -> WAIT_READY (start_nav2.sh, lifecycle nodes active, action server) -> SEND_GOAL
(recorders, goal; the acceptance deadline starts when the goal is sent, and a sent goal is never left before its
response) -> EXECUTING (feedback, terminal status, navigation timeouts, interrupts) -> CANCELING when needed ->
STOP_CONFIRM (stop-still on odometry, ground-truth pose) -> TEARDOWN -> DONE. SIGINT/SIGTERM only set a flag.
TEARDOWN always runs every step, each in its own guard (a failure is recorded as an error and the next step runs):
resume an injected pause; safety net (a goal that may be accepted and has no terminal status is canceled, and the robot
confirmed at rest, within cancel_wall_s and stop_wall_s, else the batch is aborted); transcript end; ground truth;
contacts; stop_record.sh; analyze_attempt.sh (configured thresholds); stop_nav2.sh; result.json.
Exit: 0 completed and validation pass; 10 fail; 11 inconclusive (or not analysed); 20 interrupted; 30 error;
31 error that aborts a batch (unconfirmed cancel or stop, a goal left unresolved, Nav2 or the recorders not confirmed
stopped, another Nav2 already running); 2 usage/config error, including another runner holding the lock.
The --no-* switches and --test-fault exist for the fake-node test (tests/ros_fake): they skip the simulator, the Nav2
launch, the recorders or the offline analysis, or raise an internal error on purpose; a real run uses none of them.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import yaml

from robosim_eval import contacts as contact_client
from robosim_eval import map_check
from robosim_eval.config import BaselineConfig, Scenario, load_config
from robosim_eval.evaluator import ContactPolicy, EvalInputs, Verdict, evaluate_run
from robosim_eval.nav2_params import write_params
from robosim_eval.run_io import (NAV2_SHARE, EventLog, RunLock, Transcript, loaded_inputs, now_iso, read_exit_file,
                                 runner_lock_path,
                                 write_manifest, write_resolved_config)
from robosim_eval.runner_fsm import RunStateMachine, State, StopStillTracker, doctor_retry, refresh_clock
from robosim_eval.runner_node import RunNode
from robosim_eval.runner_result import (STOP_RECORD_DATA_CODES, build_result, coverage_problems, eval_inputs,
                                        read_analysis)
from robosim_eval.sim_adapter import SimControlError
from robosim_eval.sim_math import SPAWN_ROOT, Pose2D, angle_diff, check_reset

REPO = Path(__file__).resolve().parents[1]
WSL = REPO / "scripts" / "wsl"
STATUS = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
EXIT = {"pass": 0, "fail": 10, "inconclusive": 11}
STOP_SETTLE_WALL_S = 3.0
RESULT_NOT_FOUND = 2   # simulation_interfaces/msg/Result: the entity does not exist (the one 'world not loaded' answer)
MAP_YAML = NAV2_SHARE / "maps" / "carter_warehouse_navigation.yaml"       # the launch's map: $(find-pkg-share) default
NAV2_PARAMS = NAV2_SHARE / "params" / "carter_navigation_params.yaml"
# Topic names and TF frames that record_d0.sh, stop_record.sh and analyze_attempt.read_bag hard-code: the configured
# mapping must equal them, or the online stop-still check and the offline data verdict would judge different streams.
RECORDED_TOPICS = {"clock": ("/clock", None, None), "odom": ("/chassis/odom", None, None),
                   "tf": ("/tf", "odom", "base_link")}


def script(name: str, args: List[str], log: Path, timeout: float) -> int:
    """Run one of the D0 bash scripts in its own session (a terminal Ctrl-C must not hit the teardown)."""
    with open(log, "w", encoding="utf-8") as f:
        try:
            return subprocess.run(["bash", str(WSL / name), *args], stdout=f, stderr=subprocess.STDOUT,
                                  timeout=timeout, start_new_session=True).returncode
        except subprocess.TimeoutExpired:
            f.write(f"\nrunner: {name} exceeded {timeout} s\n")
            return 124


def topic_mapping_problems(topics: Dict[str, Any]) -> List[str]:
    """Differences between the configured topic mapping and the names the recorder and the analysis use."""
    out = []
    for key, (name, parent, child) in RECORDED_TOPICS.items():
        spec = topics.get(key)
        if spec is None:
            out.append(f"topics.{key} is missing (the recorder and the analysis use {name})")
            continue
        if spec.name != name:
            out.append(f"topics.{key}.name is {spec.name!r}, but record_d0.sh, stop_record.sh and analyze_attempt.py "
                       f"use {name!r}")
        if parent and (spec.parent, spec.child) != (parent, child):
            out.append(f"topics.{key} counts {spec.parent}->{spec.child}, but the analysis uses {parent}->{child}")
    return out


class Runner:
    def __init__(self, cfg: BaselineConfig, scenario: Scenario, run_dir: Path, opts: argparse.Namespace) -> None:
        self.cfg, self.scenario, self.run_dir, self.opts = cfg, scenario, run_dir, opts
        self.interrupt: Optional[str] = None
        self.started = {"nav2": False, "record": False}
        self.facts: Dict[str, Any] = {"exit_codes": {}, "obstacles": [], "ground_truth": {}, "injections": [],
                                      "contacts": {"installed": False, "measured": False, "error": None}}
        self.limits = dataclasses.replace(cfg.run.limits, **dict(scenario.timeouts))
        self._paused_by_injection = False
        self.transcript: Optional[Transcript] = None
        self.goal_uuid: Any = None
        self.goal_future: Any = None
        self.handle: Any = None
        self.result_future: Any = None

    def _signal(self, signum, _frame) -> None:
        self.interrupt = self.interrupt or signal.Signals(signum).name

    def now(self):
        return time.monotonic(), self.rn.sim_time

    def go(self, state: State, reason: str) -> None:
        self.fsm.go(state, *self.now(), reason)
        self._sync()

    def _sync(self) -> None:
        """Write every state-machine transition not yet in events.jsonl (go, interrupt, timeout and fail alike)."""
        for h in self.fsm.history[self._logged:]:
            self.ev.write("state", state=h.state.name, reason=h.reason, fsm_t_mono=h.t_wall, fsm_t_sim=h.t_sim)
        self._logged = len(self.fsm.history)

    def run(self) -> int:
        import rclpy
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)
        self.rn = RunNode(self.cfg)
        from robosim_eval.sim_adapter import SimAdapter
        self.sim = SimAdapter(self.rn.node)
        self.ev = EventLog(self.run_dir / "events.jsonl", lambda: self.rn.sim_time)
        self.fsm = RunStateMachine(self.limits, time.monotonic(), None)
        self._logged = 0
        self._sync()
        try:
            self._prepare() and self._wait_ready() and self._send_goal() and self._execute()
        except Exception as exc:  # noqa: BLE001 - any failure must still reach the teardown; the traceback is kept
            self.ev.write("error", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
            self.fsm.fail(f"internal error: {type(exc).__name__}: {exc}", *self.now())
        finally:
            self._sync()
            self._teardown()
            self.ev.close()
            self.rn.node.destroy_node()
            rclpy.shutdown()
        return self._exit_code()

    # ---- PREPARE -------------------------------------------------------------------------------------------------
    def _prepare(self) -> bool:
        params_error = None
        if self.scenario.nav2_params:  # D5: declared change, derived from the installed vendor file Nav2 loads
            try:
                self.facts["nav2_params"] = write_params(NAV2_PARAMS, self.run_dir, self.scenario.nav2_params)
            except (OSError, ValueError) as exc:
                params_error = f"nav2 params: {exc}"
        nav2_file = Path(self.facts["nav2_params"]["file"]) if "nav2_params" in self.facts else NAV2_PARAMS
        sim = self.cfg.sim
        assets = {ob.asset: sim.obstacle_assets.get(ob.asset, sim.obstacle_usd) for ob in self.scenario.obstacles} \
            if sim else {}
        write_manifest(self.run_dir, self.run_dir.name, self.scenario.name, self.opts.config,
                       {"options": {k: getattr(self.opts, k, None) for k in ("no_sim", "no_nav2", "no_record",
                                                                             "no_analyze", "no_contacts", "test_fault")},
                        "nav2_params_effective": self.facts.get("nav2_params"),
                        "code": {"repo": str(REPO), "runner_module": str(Path(__file__).resolve())},
                        "loaded": loaded_inputs(sim.world_uri if sim else None, assets, nav2_file)})
        write_resolved_config(self.run_dir, self.cfg, self.scenario, vars(self.opts))
        if params_error:
            self.fsm.fail(params_error, *self.now())
            return False
        if not self._check_map():
            return False
        if not self.opts.no_sim and not self._reset_sim():
            return False
        attempt = 0
        while True:  # bounded re-check of a post-reset transient only (runner_fsm.doctor_retry); every attempt is kept
            attempt += 1
            rc = script("doctor.sh", ["--config", str(self.opts.config), "--out", str(self.run_dir / "doctor")],
                        self.run_dir / f"doctor-{attempt}.txt", 60)
            self.ev.write("doctor", attempt=attempt, exit_code=rc)
            if not doctor_retry(rc, attempt, 3) or self.interrupt:
                break
            time.sleep(3.0)
        self.facts["exit_codes"]["doctor"] = rc
        self.facts["doctor_attempts"] = attempt
        if rc != 0:
            self.fsm.fail(f"doctor exit {rc} after {attempt} attempt(s) (see doctor-{attempt}.txt)", *self.now())
            return False
        if self.interrupt:
            self.fsm.interrupt(self.interrupt, *self.now())
            return False
        self.go(State.WAIT_READY, "prepared")
        return True

    def _check_map(self) -> bool:
        """A5: the start (the spawn) and the goal must lie in the allowed area of the map Nav2 loads; a preset-
        unreachable goal gets its path evidence here (robosim_eval.map_check)."""
        if self.cfg.sim is None:
            self.ev.write("map_check", skipped="no sim section: no spawn pose to check (fake-node test)")
            return True
        params = Path(self.facts["nav2_params"]["file"]) if "nav2_params" in self.facts else NAV2_PARAMS
        s, g = self.cfg.sim.spawn, self.scenario.goal
        try:
            radius, how = map_check.robot_radius(params)
            res = map_check.check_scenario(map_check.load_map(MAP_YAML), radius, (s.x, s.y), (g.x, g.y),
                                           self.cfg.run.position_tolerance_m, self.scenario.preset_unreachable)
        except (OSError, ValueError) as exc:
            self.ev.write("map_check", error=f"{type(exc).__name__}: {exc}")
            self.fsm.fail(f"map check could not run: {exc}", *self.now())
            return False
        self.facts["map_check"] = {**res.to_dict(), "radius_source": how}
        self.ev.write("map_check", **self.facts["map_check"])
        if not res.ok:
            self.fsm.fail("start or goal outside the allowed area: " + "; ".join(res.problems), *self.now())
            return False
        return True

    def _spawned_entities(self) -> List[str]:
        """Names of the direct children of SPAWN_ROOT present in the stage."""
        names = self.rn.list_entities(f"^{SPAWN_ROOT}/")
        return sorted({n[len(SPAWN_ROOT) + 1:].split("/")[0] for n in names if n.startswith(SPAWN_ROOT + "/")})

    def _reset_sim(self) -> bool:
        simcfg = self.cfg.sim
        state = self.sim.get_state()
        self.ev.write("sim_state", state=state)
        try:
            self.sim.entity_state(simcfg.robot_entity)
        except SimControlError as exc:
            if exc.code != RESULT_NOT_FOUND:  # a timeout or another failure is not "world not loaded": never reload
                self.fsm.fail(f"robot state not available: {exc} (the world is reloaded only when the robot is not "
                              f"found)", *self.now())
                return False
            self.ev.write("load_world", uri=simcfg.world_uri, because=str(exc))
            if state == "playing":
                self.sim.set_state("stopped")
            self.sim.load_world(simcfg.world_uri)
        # After a possible load (the robot's bodies must exist) and before the reset (the contact report API takes
        # effect when physics restarts).
        if not self.opts.no_contacts:
            try:
                info = contact_client.install()
                self.facts["contacts"].update(installed=True, bodies=info.get("bodies"))
                self.ev.write("contacts_installed", bodies=len(info.get("bodies", [])))
            except contact_client.ContactError as exc:
                self.facts["contacts"]["error"] = str(exc)
                self.ev.write("contacts_unavailable", error=str(exc))
        self.ev.write("reset_request")
        self.ev.write("reset_done", state=self.sim.reset())
        check = None
        for _ in range(10):
            self.rn.spin(0.5)
            st = self.sim.entity_state(simcfg.robot_entity)
            check = check_reset(Pose2D(st["x"], st["y"], st["yaw"]), st["linear_speed"], st["angular_speed"],
                                simcfg.spawn, simcfg.reset_position_m, simcfg.reset_yaw_rad, simcfg.reset_speed)
            if check.ok:
                break
        self.facts["ground_truth"]["after_reset"] = st
        self.ev.write("reset_check", ok=check.ok, position_error_m=check.position_error_m,
                      yaw_error_rad=check.yaw_error_rad, reasons=list(check.reasons), pose=st)
        if not check.ok:
            self.fsm.fail("reset-check failed: " + "; ".join(check.reasons), *self.now())
            return False
        left = self._spawned_entities()  # A6: obstacles are part of the verified initial state
        self.ev.write("obstacles_after_reset", entities=left)
        if left:
            self.fsm.fail(f"the reset left entities under {SPAWN_ROOT}: {left}", *self.now())
            return False
        return self._spawn_obstacles()

    def _spawn_obstacles(self) -> bool:
        simcfg, problems, expected = self.cfg.sim, [], []
        for ob in self.scenario.obstacles:
            uri = simcfg.obstacle_assets.get(ob.asset, simcfg.obstacle_usd)
            name = self.sim.spawn_box(ob.name, ob.x, ob.y, ob.yaw, uri)
            self.facts["obstacles"].append({"entity": name, "x": ob.x, "y": ob.y, "yaw": ob.yaw, "asset": ob.asset,
                                            "uri": uri})
            self.ev.write("obstacle_spawned", entity=name, x=ob.x, y=ob.y, yaw=ob.yaw, asset=ob.asset)
            st = self.sim.entity_state(name)  # read back through sim_control: the pose must be the scenario's
            err, yaw_err = math.hypot(st["x"] - ob.x, st["y"] - ob.y), angle_diff(st["yaw"], ob.yaw)
            ok = err <= simcfg.reset_position_m and abs(yaw_err) <= simcfg.reset_yaw_rad
            self.ev.write("obstacle_check", entity=name, ok=ok, position_error_m=err, yaw_error_rad=yaw_err, pose=st)
            if not ok:
                problems.append(f"{name} is {err:.3f} m / {yaw_err:+.3f} rad from its scenario pose")
            expected.append(name[len(SPAWN_ROOT) + 1:] if name.startswith(SPAWN_ROOT + "/") else name)
        if self.scenario.obstacles:
            present = self._spawned_entities()
            self.ev.write("obstacles_listed", entities=present, expected=sorted(expected))
            if present != sorted(expected):
                problems.append(f"entities under {SPAWN_ROOT} are {present}, expected {sorted(expected)}")
        if problems:
            self.fsm.fail("obstacle layout check failed: " + "; ".join(problems), *self.now())
            return False
        if self.facts["contacts"]["installed"]:  # drop the contacts of the reset and the spawn (wheels on the ground)
            try:
                pre = contact_client.fetch()
                self.facts["contacts"]["pre_run_events"] = len(pre.get("events", []))
                self.ev.write("contacts_cleared", pre_run_events=len(pre.get("events", [])))
            except contact_client.ContactError as exc:
                self.facts["contacts"].update(installed=False, error=str(exc))
                self.ev.write("contacts_unavailable", error=str(exc))
        return True

    # ---- WAIT_READY ----------------------------------------------------------------------------------------------
    def _wait_ready(self) -> bool:
        t0 = time.monotonic()
        self.rn.clock_backward = 0  # the reset is behind us; from here a backward /clock is a data problem
        if not self.opts.no_nav2:
            extra = [f"params_file:={self.facts['nav2_params']['file']}"] if "nav2_params" in self.facts else []
            rc = script("start_nav2.sh", [str(self.run_dir), *extra], self.run_dir / "start_nav2.txt", 90)
            self.facts["exit_codes"]["start_nav2"] = rc
            self.started["nav2"] = (self.run_dir / "nav2.pid").exists()  # a partial start is stopped at teardown too
            self.ev.write("start_nav2", exit_code=rc, session_started=self.started["nav2"])
            if rc != 0:
                self.fsm.fail(f"start_nav2.sh exit {rc}" + (" (refused: another Nav2 instance is running, so the next "
                                                            "attempts would fail the same way)" if rc == 3 else ""),
                              *self.now(), abort=rc == 3)
                return False
        pending: List[str] = ["action server"]
        while True:
            self.rn.spin(0.2)
            if self.interrupt:
                self.fsm.interrupt(self.interrupt, *self.now())
                return False
            if self.rn.nav.server_is_ready():
                pending = [] if self.opts.no_nav2 else self.rn.lifecycle_active()
                if not pending:
                    break
            to = self.fsm.check(*self.now())
            if to:
                self.ev.write("not_ready", pending=pending)
                self.fsm.timeout(to, *self.now())
                return False
            time.sleep(0.5)
        if "nav2_params" in self.facts:  # the declared change must be what the running node actually uses
            for ch in self.facts["nav2_params"]["changes"]:
                ch["in_effect"] = self.rn.get_param(ch["node"], ch["param"])
            self.ev.write("nav2_params_checked", changes=self.facts["nav2_params"]["changes"])
            wrong = [c for c in self.facts["nav2_params"]["changes"] if c["in_effect"] != c["new"]]
            if wrong:
                self.fsm.fail(f"declared Nav2 parameter not in effect: {wrong}", *self.now())
                return False
        self.facts["nav2_ready_wall_s"] = round(time.monotonic() - t0, 2)
        self.go(State.SEND_GOAL, f"nav2 ready after {self.facts['nav2_ready_wall_s']} s")
        return True

    # ---- SEND_GOAL -----------------------------------------------------------------------------------------------
    def _send_goal(self) -> bool:
        if not self.opts.no_record:
            rc = script("record_d0.sh", [str(self.run_dir), str(int(self.cfg.run.record_cap_s))],
                        self.run_dir / "record_start.txt", 60)
            self.facts["exit_codes"]["record_d0"] = rc
            self.started["record"] = (self.run_dir / "record.pids").exists()  # recorders that did start are stopped
            self.ev.write("record_start", exit_code=rc)
            if rc != 0:
                self.fsm.fail(f"record_d0.sh exit {rc}", *self.now())
                return False
        # The recorder start blocked for seconds without spinning: refresh the simulation time before it becomes the
        # base of the navigation limit and of the injections (goal acceptance was 1.1-2.1 s sim late before, D5).
        self.ev.write("clock_refreshed", ok=refresh_clock(self.rn.spin, lambda: self.rn.clock_msgs))
        if self.interrupt:  # the last check before the goal exists: an interrupt up to here leaves no goal behind
            self.fsm.interrupt(self.interrupt, *self.now())
            return False
        g = self.scenario.goal
        goal = self.rn.NavigateToPose.Goal()
        goal.pose.header.frame_id = self.cfg.run.frame
        goal.pose.pose.position.x, goal.pose.pose.position.y = g.x, g.y
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = math.sin(g.yaw / 2), math.cos(g.yaw / 2)
        self.transcript = Transcript(self.run_dir)
        self.transcript.start(g.x, g.y, g.yaw, "/navigate_to_pose")
        self.goal_uuid = self.rn.new_goal_uuid()
        gid = bytes(self.goal_uuid.uuid).hex()
        self.goal_future = self.rn.nav.send_goal_async(goal, feedback_callback=self.rn.on_feedback,
                                                       goal_uuid=self.goal_uuid)
        self.facts["goal_sent"] = {"id": gid, "wall": now_iso()}
        self.ev.write("goal_sent", x=g.x, y=g.y, yaw=g.yaw, frame=self.cfg.run.frame, goal_id=gid)
        self.fsm.restart(f"goal {gid} sent: the acceptance deadline starts now", *self.now())
        self._sync()
        while not self.goal_future.done():  # an interrupt now waits for the response (then cancels an accepted goal)
            self.rn.spin(0.05)
            if self.goal_future.done():
                break
            to = self.fsm.check(*self.now())
            if to:
                self.ev.write("timeout", name=to)
                self.fsm.timeout(to, *self.now())  # the teardown safety net resolves the goal
                return False
        self.handle = self.goal_future.result()
        if not self.handle.accepted:
            self.facts["rejected"] = True
            self.transcript.line("Goal was rejected by server")
            self.go(State.TEARDOWN, "goal rejected")
            if self.interrupt:
                self.fsm.interrupt(self.interrupt, *self.now())
            return False
        self._accepted()
        self.go(State.EXECUTING, f"goal accepted {self.facts['goal_id']}")
        return True

    def _accepted(self) -> None:
        gid = bytes(self.handle.goal_id.uuid).hex()
        self.facts["goal_id"], self.facts["accept_sim"] = gid, self.rn.sim_time
        self.transcript.line(f"Goal accepted with ID: {gid}")
        self.result_future = self.handle.get_result_async()

    # ---- EXECUTING / CANCELING / STOP_CONFIRM --------------------------------------------------------------------
    def _test_fault(self, where: str) -> None:
        """--test-fault (fake-node test only): an internal error 1 s after entering the named state."""
        if getattr(self.opts, "test_fault", None) == where and self.fsm.state.name.lower() == where \
                and time.monotonic() - self.fsm.entered.t_wall >= 1.0:
            raise RuntimeError(f"injected test fault (--test-fault {where})")

    def _inject(self) -> None:
        """Scenario fault injections (labelled in events.jsonl): a planned cancel and a sim pause/resume."""
        inj, t0, t = self.scenario.inject, self.facts.get("accept_sim"), self.rn.sim_time
        if not inj or t0 is None or t is None:
            return
        done = {i["kind"] for i in self.facts["injections"]}
        if self.fsm.state is State.EXECUTING and "cancel_after_sim_s" in inj and t - t0 >= inj["cancel_after_sim_s"]:
            self.facts["injections"].append({"kind": "cancel", "sim": t})
            self.ev.write("inject_cancel", after_sim_s=t - t0)
            self.fsm.cancel(f"injected cancel {t - t0:.2f} s (sim) after acceptance", *self.now())
            self._sync()
        if self.fsm.state is State.EXECUTING and "pause_after_sim_s" in inj and "pause" not in done \
                and t - t0 >= inj["pause_after_sim_s"]:
            # recorded before the call: a pause that takes effect but whose reply fails is still resumed at teardown
            self.facts["injections"].append({"kind": "pause", "sim": t, "wall": time.monotonic()})
            self._paused_by_injection = True
            self.ev.write("inject_pause_request", after_sim_s=t - t0)
            self.ev.write("inject_pause", state=self.sim.set_state("paused"), after_sim_s=t - t0)
        self._service_resume()

    def _service_resume(self) -> bool:
        """End an injected pause after pause_wall_s (in any state); True while the simulation is still paused by it."""
        if not self._paused_by_injection:
            return False
        started = next(i["wall"] for i in self.facts["injections"] if i["kind"] == "pause")
        if time.monotonic() - started < self.scenario.inject.get("pause_wall_s", 0.0):
            return True
        self.ev.write("inject_resume", state=self.sim.set_state("playing"))
        self.facts["injections"].append({"kind": "resume", "wall": time.monotonic()})
        self._paused_by_injection = False
        if self.fsm.state is State.STOP_CONFIRM:  # no odometry could arrive while paused
            self.fsm.restart("simulation resumed after the injected pause: the stop deadline starts now", *self.now())
            self._sync()
        return False

    def _record_terminal(self, res: Any, source: str) -> None:
        name = STATUS.get(res.status, f"UNKNOWN({res.status})")
        self.transcript.line(f"error_code: {res.result.error_code}")
        self.transcript.line(f"error_msg: '{res.result.error_msg}'")
        self.transcript.line(f"Goal finished with status: {name}")
        self.facts["terminal_sim"] = self.rn.sim_time  # stop-still is only judged on samples after this
        self.facts["terminal"] = {"status": res.status, "name": name, "error_code": res.result.error_code,
                                  "error_msg": res.result.error_msg, "feedback_count": self.rn.feedback_count,
                                  "last_feedback": self.rn.last_feedback, "source": source}

    def _execute(self) -> bool:
        canceled = False
        while self.fsm.state in (State.EXECUTING, State.CANCELING):
            self.rn.spin(0.05)
            self._test_fault("executing")
            launch_exit = read_exit_file(self.run_dir / "nav2.exit") if self.started["nav2"] else None
            if launch_exit is not None:  # the launch wrapper records the exit only when ros2 launch has ended
                self.fsm.fail(f"Nav2 launch exited during the run (exit {launch_exit})", *self.now())
                return False
            if not self.opts.no_sim:
                self._inject()
            if self.result_future.done():
                self._record_terminal(self.result_future.result(), "action client")
                self.go(State.STOP_CONFIRM, f"terminal status {self.facts['terminal']['name']}")
                break
            if self.fsm.state is State.EXECUTING and self.interrupt:
                self.fsm.interrupt(self.interrupt, *self.now())
                self._sync()
            to = self.fsm.check(*self.now())
            if to:
                self.ev.write("timeout", name=to)
                self.fsm.timeout(to, *self.now())
                self._sync()
                if self.fsm.state is State.TEARDOWN:
                    return False
            if self.fsm.state is State.CANCELING and not canceled:
                self.handle.cancel_goal_async()
                self.ev.write("cancel_requested")
                canceled = True
        return self._confirm_stop()

    def _wait_at_rest(self, after_sim: Optional[float],
                      expired: Callable[[], Optional[str]]) -> Tuple[Optional[float], Dict[str, Any], Optional[str]]:
        """Feed each odometry sample stamped after `after_sim` once, in stamp order, to the stop-still rule until it
        confirms (confirmation time, diagnostics, None) or `expired` names a deadline (None, diagnostics, name). An
        injected pause is ended here too, and no deadline is judged while it lasts."""
        r = self.cfg.run
        tracker = StopStillTracker(r.stop_linear_mps, r.stop_angular_radps, r.stop_hold_sim_s, r.stop_max_gap_sim_s)
        last_fed = after_sim
        diag = {"start_after": after_sim, "fed": 0, "max_gap": 0.0, "max_v": 0.0, "max_w": 0.0, "buffer_first": None,
                "buffer_last": None}
        while True:
            self.rn.spin(0.05)
            paused = self._service_resume() if not self.opts.no_sim else False
            buf = list(self.rn.odom)
            if buf:
                diag["buffer_first"], diag["buffer_last"] = buf[0][0], buf[-1][0]
            for t, v, w in buf:
                if last_fed is None or t > last_fed:
                    if diag["fed"]:
                        diag["max_gap"] = max(diag["max_gap"], t - last_fed)
                    diag["fed"] += 1
                    diag["max_v"], diag["max_w"] = max(diag["max_v"], v), max(diag["max_w"], w)
                    last_fed = t
                    if tracker.update(t, v, w) is not None:
                        break
            if tracker.confirmed_at is not None:
                return tracker.confirmed_at, diag, None
            to = None if paused else expired()
            if to:
                return None, {**diag, "last_fed": last_fed}, to

    def _confirm_stop(self) -> bool:
        if self.fsm.state is not State.STOP_CONFIRM:
            return False
        at, diag, to = self._wait_at_rest(self.facts.get("terminal_sim"), lambda: self.fsm.check(*self.now()))
        if at is None:
            self.ev.write("timeout", name=to, stop_still_diagnostics=diag)
            self.fsm.timeout(to, *self.now())
            self._sync()
            return False
        if not self.opts.no_sim:
            gt = self.sim.entity_state(self.cfg.sim.robot_entity)
            gt["sim_time_paired"] = self.rn.sim_time
            g = self.scenario.goal
            gt["error_to_goal_m"] = math.hypot(gt["x"] - g.x, gt["y"] - g.y)
            self.facts["ground_truth"]["at_stop"] = gt
            self.ev.write("ground_truth", **gt)
        self.facts["stop_confirmed_sim"] = at
        self.go(State.TEARDOWN, f"robot at rest (stop-still confirmed at sim {at:.3f})")
        return True

    # ---- TEARDOWN ------------------------------------------------------------------------------------------------
    def _teardown(self) -> None:
        if self.fsm.state is not State.TEARDOWN:
            self.fsm.fail(f"teardown reached from {self.fsm.state.name}", *self.now())
        self._sync()
        for name, step, abort in (("resume", self._td_resume, True), ("safety_net", self._td_safety_net, True),
                                  ("transcript", self._td_transcript, False),
                                  ("ground_truth", self._td_ground_truth, False), ("contacts", self._td_contacts, False),
                                  ("stop_record", self._td_stop_record, True), ("analyze", self._td_analyze, False),
                                  ("stop_nav2", self._td_stop_nav2, True)):
            self._step(name, step, abort)
        self._sync()
        self.go(State.DONE, "teardown finished")
        self._step("result", self._write_result, False)  # last artifact: it includes the history up to DONE

    def _step(self, name: str, fn: Callable[[], None], abort: bool) -> None:
        """Run one teardown step; a failure is recorded (event + error; abort when it may leave a goal, a paused
        simulation or a resident process behind) and the next step still runs."""
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - one failing teardown step must not skip the others
            self.fsm.fail(f"teardown step {name} failed: {type(exc).__name__}: {exc}", *self.now(), abort=abort)
            try:
                self.ev.write("teardown_error", step=name, error=f"{type(exc).__name__}: {exc}",
                              traceback=traceback.format_exc())
            except (OSError, ValueError) as log_exc:
                self.fsm.fail(f"events.jsonl write failed: {log_exc}", *self.now())
        self._sync()

    def _td_resume(self) -> None:
        if not self._paused_by_injection:  # never leave the simulator paused, even if the pause reply failed
            return
        state = self.sim.get_state()
        if state != "playing":
            state = self.sim.set_state("playing")
        self.ev.write("inject_resume", state=state, reason="teardown")
        self.facts["injections"].append({"kind": "resume", "wall": time.monotonic(), "reason": "teardown"})
        self._paused_by_injection = False

    def _td_safety_net(self) -> None:
        """A goal that may have been accepted and has no terminal status is canceled and the stop confirmed (A5: an
        unconfirmed cancel or stop aborts the batch). Covers an interrupt or accept timeout after sending, and an
        internal error while the goal ran."""
        f = self.facts
        if "goal_sent" not in f or f.get("rejected") or {"cancel_timeout", "stop_timeout"} & set(self.fsm.errors):
            return  # nothing sent, nothing accepted, or the batch is already aborted for this goal
        net: Dict[str, Any] = f.setdefault("safety_net", {})
        if "terminal" not in f:
            net["cancel"] = "confirmed" if self._net_cancel() else "not confirmed"
            self.ev.write("safety_net", step="cancel", result=net["cancel"],
                          terminal=(f.get("terminal") or {}).get("name"), rejected=bool(f.get("rejected")))
            if net["cancel"] != "confirmed":
                self.fsm.fail(f"safety net: goal {f['goal_sent']['id']} has no confirmed terminal status within "
                              f"{self.limits.cancel_wall_s} s after the cancel", *self.now(), abort=True)
                return
            if f.get("rejected"):
                return
        if "stop_confirmed_sim" not in f:
            end = time.monotonic() + self.limits.stop_wall_s
            at, diag, _ = self._wait_at_rest(f.get("terminal_sim"),
                                             lambda: "stop_timeout" if time.monotonic() > end else None)
            net["stop"] = "confirmed" if at is not None else "not confirmed"
            self.ev.write("safety_net", step="stop", result=net["stop"], stop_still_diagnostics=diag)
            if at is None:
                self.fsm.fail(f"safety net: robot not confirmed at rest within {self.limits.stop_wall_s} s",
                              *self.now(), abort=True)
                return
            f["stop_confirmed_sim"] = at

    def _net_cancel(self) -> bool:
        """Cancel the sent goal and wait (cancel_wall_s) for its terminal status. With the goal response still missing,
        cancel it by id and ask its result by id directly, again every second (a late acceptance is canceled too)."""
        uid = bytes(self.goal_uuid.uuid)
        end, next_raw, raw, cancel_sent = time.monotonic() + self.limits.cancel_wall_s, 0.0, None, False
        while time.monotonic() < end:
            self.rn.spin(0.05)
            if self.handle is None and self.goal_future.done():
                self.handle = self.goal_future.result()
            if self.handle is not None:
                if not self.handle.accepted:
                    self.facts["rejected"] = True
                    self.transcript.line("Goal was rejected by server")
                    return True
                if self.result_future is None:  # the response came after the SEND_GOAL deadline
                    self._accepted()
                    self.ev.write("goal_accepted_late", goal_id=self.facts["goal_id"])
                if self.result_future.done():
                    self._record_terminal(self.result_future.result(), "safety net (action client)")
                    return True
                if not cancel_sent:
                    self.handle.cancel_goal_async()
                    self.ev.write("cancel_requested", source="safety net")
                    cancel_sent = True
                continue
            if raw is not None and raw.done():
                res = raw.result()
                if res is not None and res.status in STATUS:
                    self._record_terminal(res, "safety net (get_result by goal id)")
                    return True
                raw = None  # STATUS_UNKNOWN: the server does not know the goal (yet); cancel and ask again
            if raw is None and time.monotonic() >= next_raw:
                self.rn.cancel_by_id(uid)
                raw, next_raw = self.rn.result_by_id(uid), time.monotonic() + 1.0
        return False

    def _td_transcript(self) -> None:
        if self.transcript is not None and not self.transcript.closed:
            self.transcript.end(0 if "terminal" in self.facts else None)

    def _td_ground_truth(self) -> None:
        if self.opts.no_sim or "at_stop" in self.facts["ground_truth"]:
            return
        try:
            gt = self.sim.entity_state(self.cfg.sim.robot_entity)
        except SimControlError as exc:  # recorded; the verdict then has no ground truth
            self.ev.write("ground_truth_unavailable", error=str(exc))
            return
        gt["sim_time_paired"] = self.rn.sim_time
        self.facts["ground_truth"]["at_end"] = gt
        self.ev.write("ground_truth_at_end", **gt)

    def _td_contacts(self) -> None:
        if not self.facts["contacts"]["installed"]:
            return
        try:
            got = contact_client.fetch()
        except contact_client.ContactError as exc:
            self.facts["contacts"].update(measured=False, error=str(exc))
            self.ev.write("contacts_unavailable", error=str(exc))
            return
        self.facts["contacts"].update(measured=True, events=got.get("events", []), dropped=got.get("dropped", 0),
                                      found_pairs=contact_client.found_pairs(got),
                                      persist_pairs=got.get("persist_pairs", []))
        self.ev.write("contacts_fetched", events=len(got.get("events", [])), dropped=got.get("dropped", 0))

    def _td_stop_record(self) -> None:
        if not self.started["record"]:
            return
        if "stop_confirmed_sim" in self.facts:
            time.sleep(STOP_SETTLE_WALL_S)  # keep recording briefly so the offline analysis sees the whole rest window
        rc = self.facts["exit_codes"]["stop_record"] = script("stop_record.sh", [str(self.run_dir)],
                                                               self.run_dir / "stop_record.txt", 180)
        self.ev.write("record_stop", exit_code=rc)
        if rc != 0 and rc not in STOP_RECORD_DATA_CODES:  # 4/5/6 are data problems, judged in _evaluate
            self.fsm.fail(f"stop_record.sh exit {rc}: the recorders were not confirmed stopped", *self.now(),
                          abort=True)

    def _td_analyze(self) -> None:
        if self.opts.no_analyze or not (self.run_dir / "rosbag").exists():
            return
        g, r = self.scenario.goal, self.cfg.run  # the configured thresholds, not the analyzer's defaults
        args = [str(self.run_dir), "--goal", str(g.x), str(g.y), str(g.yaw),
                "--tolerance", str(r.position_tolerance_m),
                "--stop-lin", str(r.stop_linear_mps), "--stop-ang", str(r.stop_angular_radps),
                "--stop-hold", str(r.stop_hold_sim_s), "--max-stop-gap", str(r.stop_max_gap_sim_s),
                "--dropout", str(r.dropout_wall_s)]
        if self.cfg.sim is not None:
            s = self.cfg.sim.spawn
            args += ["--spawn", str(s.x), str(s.y), str(s.yaw)]
        self.facts["exit_codes"]["analyze"] = script("analyze_attempt.sh", args, self.run_dir / "analyze.txt", 300)
        self.ev.write("analyze", exit_code=self.facts["exit_codes"]["analyze"])

    def _td_stop_nav2(self) -> None:
        if not self.started["nav2"]:
            return
        before = read_exit_file(self.run_dir / "nav2.exit")  # set already: the launch ended before our stop request
        rc = self.facts["exit_codes"]["stop_nav2"] = script("stop_nav2.sh", [str(self.run_dir)],
                                                             self.run_dir / "stop_nav2.txt", 180)
        # the stop script's result says whether the processes are gone (cleanup); Nav2's own exit is kept apart
        self.facts["nav2"] = {"stop_script_exit": rc, "launch_exit": read_exit_file(self.run_dir / "nav2.exit"),
                              "launch_exited_before_stop": before is not None}
        self.ev.write("nav2_stop", exit_code=rc, **self.facts["nav2"])
        if rc != 0:
            self.fsm.fail(f"stop_nav2.sh exit {rc}: Nav2 was not confirmed stopped", *self.now(), abort=True)

    # ---- RESULT (robosim_eval.runner_result) --------------------------------------------------------------------
    def _write_result(self) -> None:
        analysis, error = read_analysis(self.run_dir, self.facts["exit_codes"].get("analyze"))
        if error:
            self.facts["analysis_error"] = error
        verdict, inputs = self._evaluate(analysis)
        result = build_result(self.run_dir.name, self.cfg, self.scenario, self.facts, self.fsm, verdict, inputs,
                              analysis)
        (self.run_dir / "result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        self.result = result

    def _evaluate(self, analysis: Optional[Dict[str, Any]]) -> Tuple[Verdict, EvalInputs]:
        """D3 verdict from the runner facts, ground truth, contact data, the map check and the offline analysis."""
        coverage = coverage_problems(self.run_dir, self.facts, self.opts, self.cfg, analysis)
        inputs = eval_inputs(self.cfg, self.scenario, self.facts, self.fsm, self.rn.clock_backward, coverage, analysis)
        run = self.cfg.run
        return evaluate_run(inputs, ContactPolicy(run.contact_robot_root, tuple(run.contact_ignore_prefixes))), inputs

    def _exit_code(self) -> int:
        if self.fsm.execution_status == "error":
            return 31 if self.fsm.abort_batch else 30
        if self.fsm.execution_status == "interrupted":
            return 20
        return EXIT.get(getattr(self, "result", {}).get("validation_status"), 11)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RoboSim Eval D2 single-run runner")
    p.add_argument("--scenario", required=True)
    p.add_argument("--config", default=str(REPO / "configs" / "baseline.yaml"))
    p.add_argument("--out", default=str(REPO / "artifacts" / "d2" / "runs"))
    for flag in ("no-sim", "no-nav2", "no-record", "no-analyze", "no-contacts"):
        p.add_argument(f"--{flag}", action="store_true")
    p.add_argument("--test-fault", choices=["executing"], help="fake-node test only (needs --no-sim)")
    a = p.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, yaml.YAMLError) as exc:
        print(f"config error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if cfg.run is None or a.scenario not in cfg.scenarios:
        print(f"config has no run section or no scenario {a.scenario!r} (have: {sorted(cfg.scenarios)})", file=sys.stderr)
        return 2
    mapping = topic_mapping_problems(cfg.topics)
    if mapping:
        print("config error: the topic mapping differs from what the recorder and the analysis use: "
              + "; ".join(mapping), file=sys.stderr)
        return 2
    if a.test_fault and not a.no_sim:
        print("--test-fault is for the fake-node test only (use it with --no-sim)", file=sys.stderr)
        return 2
    if a.no_sim:
        a.no_contacts = True  # contact data comes from inside Isaac
    if not a.no_sim and cfg.sim is None:
        print("config has no sim section (use --no-sim for the fake-node test)", file=sys.stderr)
        return 2
    run_dir = Path(a.out) / f"{a.scenario}-{time.strftime('%Y%m%d-%H%M%S')}"
    lock = RunLock(runner_lock_path(os.environ.get("ROS_DOMAIN_ID", "0")))
    owner = lock.acquire({"pid": os.getpid(), "run_dir": str(run_dir), "scenario": a.scenario, "since": now_iso()})
    if owner is not None:
        print(f"another runner is active on this ROS domain ({lock.path}: {owner}); refusing to touch the simulator "
              f"it is using", file=sys.stderr)
        return 2
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        print(f"run dir: {run_dir}", flush=True)
        runner = Runner(cfg, cfg.scenarios[a.scenario], run_dir, a)
        rc = runner.run()
    finally:
        lock.release()
    r = getattr(runner, "result", {})
    print(json.dumps({"run_dir": str(run_dir), "exit": rc, "execution_status": r.get("execution_status"),
                      "task_outcome": r.get("task_outcome"), "validation_status": r.get("validation_status"),
                      "errors": runner.fsm.errors}), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
