"""D2 single-run runner: one config-driven A->B navigation with a timeout-guarded state machine and a full teardown.

Run in WSL through scripts/wsl/run_scenario.sh (it sources the ROS and Fast DDS environment):
  python3 -m robosim_eval.runner --scenario normal [--config configs/baseline.yaml] [--out artifacts/d2/runs]
         [--no-sim] [--no-nav2] [--no-record] [--no-analyze]
Steps (robosim_eval.runner_fsm): PREPARE (manifest, resolved config, sim reset + reset-check, obstacles, doctor)
-> WAIT_READY (start_nav2.sh, lifecycle nodes active, action server) -> SEND_GOAL (recorders, goal, accept timeout)
-> EXECUTING (feedback, terminal status, navigation timeouts, interrupts) -> CANCELING when needed -> STOP_CONFIRM
(stop-still on odometry, ground-truth pose) -> TEARDOWN (always: transcript end, stop_record.sh, analyze_attempt.sh,
stop_nav2.sh, result.json merge) -> DONE. SIGINT/SIGTERM only set a flag, so the run is always closed out.
Exit: 0 completed and validation pass; 10 fail; 11 inconclusive (or not analysed); 20 interrupted; 30 error;
31 error that aborts a batch (unconfirmed cancel or stop); 2 usage/config error.
The --no-* switches exist for the fake-node test (tests/ros_fake): they skip the simulator, the Nav2 launch, the
recorders or the offline analysis; a real run uses none of them.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from robosim_eval import contacts as contact_client
from robosim_eval.config import BaselineConfig, Scenario, load_config
from robosim_eval.evaluator import ContactPolicy, EvalInputs, evaluate_run
from robosim_eval.nav2_params import write_params
from robosim_eval.run_io import VENDOR_PKG, EventLog, Transcript, to_plain, write_manifest, write_resolved_config
from robosim_eval.runner_fsm import RunStateMachine, State, StopStillTracker, append_sample, doctor_retry

REPO = Path(__file__).resolve().parents[1]
WSL = REPO / "scripts" / "wsl"
NAV2_NODES = ["map_server", "amcl", "planner_server", "controller_server", "bt_navigator", "behavior_server",
              "smoother_server", "velocity_smoother", "collision_monitor", "waypoint_follower"]  # = check_nav2_ready.sh
STATUS = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
EXIT = {"pass": 0, "fail": 10, "inconclusive": 11}
STOP_SETTLE_WALL_S = 3.0


def script(name: str, args: List[str], log: Path, timeout: float) -> int:
    """Run one of the D0 bash scripts in its own session (a terminal Ctrl-C must not hit the teardown)."""
    with open(log, "w", encoding="utf-8") as f:
        try:
            return subprocess.run(["bash", str(WSL / name), *args], stdout=f, stderr=subprocess.STDOUT,
                                  timeout=timeout, start_new_session=True).returncode
        except subprocess.TimeoutExpired:
            f.write(f"\nrunner: {name} exceeded {timeout} s\n")
            return 124


class RunNode:
    """rclpy node with the /clock and odometry subscriptions and the NavigateToPose action client."""

    def __init__(self, cfg: BaselineConfig) -> None:
        import rclpy
        from nav2_msgs.action import NavigateToPose
        from nav_msgs.msg import Odometry
        from rclpy.action import ActionClient
        from rclpy.node import Node
        from rclpy.qos import qos_profile_sensor_data
        from rosgraph_msgs.msg import Clock
        self.rclpy = rclpy
        self.node = Node("robosim_runner")
        self.sim_time: Optional[float] = None
        self.clock_backward = 0
        self.odom: List[tuple] = []
        self.feedback_count = 0
        self.last_feedback: Dict[str, Any] = {}
        self.node.create_subscription(Clock, cfg.topics["clock"].name, self._on_clock, qos_profile_sensor_data)
        self.node.create_subscription(Odometry, cfg.topics["odom"].name, self._on_odom, qos_profile_sensor_data)
        self.nav = ActionClient(self.node, NavigateToPose, "/navigate_to_pose")
        self.NavigateToPose = NavigateToPose

    def _on_clock(self, msg) -> None:
        t = msg.clock.sec + msg.clock.nanosec * 1e-9
        if self.sim_time is not None and t < self.sim_time:
            self.clock_backward += 1
        self.sim_time = t

    def _on_odom(self, msg) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        tw = msg.twist.twist
        append_sample(self.odom, (t, math.hypot(tw.linear.x, tw.linear.y), abs(tw.angular.z)), 400)

    def on_feedback(self, fb) -> None:
        self.feedback_count += 1
        f = fb.feedback
        self.last_feedback = {"distance_remaining": f.distance_remaining, "recoveries": f.number_of_recoveries}

    def spin(self, seconds: float = 0.05) -> None:
        self.rclpy.spin_once(self.node, timeout_sec=seconds)

    def get_param(self, node_name: str, name: str, timeout: float = 5.0) -> Any:
        """Current value of one parameter of a running node (GetParameters service); None when unavailable."""
        from rcl_interfaces.srv import GetParameters
        from rclpy.parameter import parameter_value_to_python
        cli = self.node.create_client(GetParameters, f"/{node_name}/get_parameters")
        try:
            if not cli.wait_for_service(timeout_sec=timeout):
                return None
            fut = cli.call_async(GetParameters.Request(names=[name]))
            self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
            values = fut.result().values if fut.done() and fut.result() is not None else []
            return parameter_value_to_python(values[0]) if values else None
        finally:
            self.node.destroy_client(cli)

    def lifecycle_active(self, timeout: float = 1.0) -> List[str]:
        """Names of the Nav2 lifecycle nodes that are not (yet) active."""
        from lifecycle_msgs.srv import GetState
        pending = []
        for name in NAV2_NODES:
            cli = self.node.create_client(GetState, f"/{name}/get_state")
            ok = False
            if cli.wait_for_service(timeout_sec=timeout):
                fut = cli.call_async(GetState.Request())
                self.rclpy.spin_until_future_complete(self.node, fut, timeout_sec=timeout)
                ok = fut.done() and fut.result() is not None and fut.result().current_state.label == "active"
            self.node.destroy_client(cli)
            if not ok:
                pending.append(name)
        return pending


class Runner:
    def __init__(self, cfg: BaselineConfig, scenario: Scenario, run_dir: Path, opts: argparse.Namespace) -> None:
        self.cfg, self.scenario, self.run_dir, self.opts = cfg, scenario, run_dir, opts
        self.interrupt: Optional[str] = None
        self.started = {"nav2": False, "record": False}
        self.facts: Dict[str, Any] = {"exit_codes": {}, "obstacles": [], "ground_truth": {}, "injections": [],
                                      "contacts": {"installed": False, "measured": False, "error": None}}
        self.limits = dataclasses.replace(cfg.run.limits, **dict(scenario.timeouts))
        self._paused_by_injection = False

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
        self.transcript: Optional[Transcript] = None
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
        if self.scenario.nav2_params:  # D5: declared change, derived from the vendor file; checked once Nav2 is up
            try:
                self.facts["nav2_params"] = write_params(VENDOR_PKG / "params" / "carter_navigation_params.yaml",
                                                         self.run_dir, self.scenario.nav2_params)
            except (OSError, ValueError) as exc:
                params_error = f"nav2 params: {exc}"
        write_manifest(self.run_dir, self.run_dir.name, self.scenario.name, self.opts.config,
                       {"options": {k: getattr(self.opts, k) for k in ("no_sim", "no_nav2", "no_record", "no_analyze",
                                                                        "no_contacts")},
                        "nav2_params_effective": self.facts.get("nav2_params")})
        write_resolved_config(self.run_dir, self.cfg, self.scenario, vars(self.opts))
        if params_error:
            self.fsm.fail(params_error, *self.now())
            return False
        if not self.opts.no_sim:
            if not self._reset_sim():
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

    def _reset_sim(self) -> bool:
        from robosim_eval.sim_math import Pose2D, check_reset
        simcfg = self.cfg.sim
        state = self.sim.get_state()
        self.ev.write("sim_state", state=state)
        if not self.opts.no_contacts:  # before the reset: the contact report API takes effect when physics restarts
            try:
                info = contact_client.install()
                self.facts["contacts"].update(installed=True, bodies=info.get("bodies"))
                self.ev.write("contacts_installed", bodies=len(info.get("bodies", [])))
            except contact_client.ContactError as exc:
                self.facts["contacts"]["error"] = str(exc)
                self.ev.write("contacts_unavailable", error=str(exc))
        try:
            self.sim.entity_state(simcfg.robot_entity)
        except Exception as exc:  # noqa: BLE001 - robot not found: the world is not loaded yet
            self.ev.write("load_world", uri=simcfg.world_uri, because=str(exc))
            if state == "playing":
                self.sim.set_state("stopped")
            self.sim.load_world(simcfg.world_uri)
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
        for ob in self.scenario.obstacles:
            uri = simcfg.obstacle_assets.get(ob.asset, simcfg.obstacle_usd)
            name = self.sim.spawn_box(ob.name, ob.x, ob.y, ob.yaw, uri)
            self.facts["obstacles"].append({"entity": name, "x": ob.x, "y": ob.y, "yaw": ob.yaw, "asset": ob.asset,
                                            "uri": uri})
            self.ev.write("obstacle_spawned", entity=name, x=ob.x, y=ob.y, yaw=ob.yaw, asset=ob.asset)
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
            self.ev.write("start_nav2", exit_code=rc)
            if rc != 0:
                self.fsm.fail(f"start_nav2.sh exit {rc}", *self.now())
                return False
            self.started["nav2"] = True
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
            self.ev.write("record_start", exit_code=rc)
            if rc != 0:
                self.fsm.fail(f"record_d0.sh exit {rc}", *self.now())
                return False
            self.started["record"] = True
        g = self.scenario.goal
        goal = self.rn.NavigateToPose.Goal()
        goal.pose.header.frame_id = self.cfg.run.frame
        goal.pose.pose.position.x, goal.pose.pose.position.y = g.x, g.y
        goal.pose.pose.orientation.z, goal.pose.pose.orientation.w = math.sin(g.yaw / 2), math.cos(g.yaw / 2)
        self.transcript = Transcript(self.run_dir)
        self.transcript.start(g.x, g.y, g.yaw, "/navigate_to_pose")
        fut = self.rn.nav.send_goal_async(goal, feedback_callback=self.rn.on_feedback)
        self.ev.write("goal_sent", x=g.x, y=g.y, yaw=g.yaw, frame=self.cfg.run.frame)
        while not fut.done():
            self.rn.spin(0.05)
            if self.interrupt:
                self.fsm.interrupt(self.interrupt, *self.now())
                return False
            to = self.fsm.check(*self.now())
            if to:
                self.fsm.timeout(to, *self.now())
                return False
        self.handle = fut.result()
        if not self.handle.accepted:
            self.facts["rejected"] = True
            self.transcript.line("Goal was rejected by server")
            self.go(State.TEARDOWN, "goal rejected")
            return False
        gid = bytes(self.handle.goal_id.uuid).hex()
        self.facts["goal_id"], self.facts["accept_sim"] = gid, self.rn.sim_time
        self.transcript.line(f"Goal accepted with ID: {gid}")
        self.result_future = self.handle.get_result_async()
        self.go(State.EXECUTING, f"goal accepted {gid}")
        return True

    # ---- EXECUTING / CANCELING / STOP_CONFIRM --------------------------------------------------------------------
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
        if "pause_after_sim_s" in inj and "pause" not in done and t - t0 >= inj["pause_after_sim_s"]:
            self.ev.write("inject_pause", state=self.sim.set_state("paused"), after_sim_s=t - t0)
            self.facts["injections"].append({"kind": "pause", "sim": t, "wall": time.monotonic()})
            self._paused_by_injection = True
        if self._paused_by_injection:
            started = next(i["wall"] for i in self.facts["injections"] if i["kind"] == "pause")
            if time.monotonic() - started >= inj.get("pause_wall_s", 0.0):
                self.ev.write("inject_resume", state=self.sim.set_state("playing"))
                self.facts["injections"].append({"kind": "resume", "wall": time.monotonic()})
                self._paused_by_injection = False

    def _execute(self) -> bool:
        canceled = False
        while self.fsm.state in (State.EXECUTING, State.CANCELING):
            self.rn.spin(0.05)
            if not self.opts.no_sim:
                self._inject()
            if self.result_future.done():
                res = self.result_future.result()
                name = STATUS.get(res.status, f"UNKNOWN({res.status})")
                self.transcript.line(f"error_code: {res.result.error_code}")
                self.transcript.line(f"error_msg: '{res.result.error_msg}'")
                self.transcript.line(f"Goal finished with status: {name}")
                self.facts["terminal_sim"] = self.rn.sim_time  # stop-still is only judged on samples after this
                self.facts["terminal"] = {"status": res.status, "name": name, "error_code": res.result.error_code,
                                          "error_msg": res.result.error_msg, "feedback_count": self.rn.feedback_count,
                                          "last_feedback": self.rn.last_feedback}
                self.go(State.STOP_CONFIRM, f"terminal status {name}")
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

    def _confirm_stop(self) -> bool:
        r = self.cfg.run
        tracker = StopStillTracker(r.stop_linear_mps, r.stop_angular_radps, r.stop_hold_sim_s, r.stop_max_gap_sim_s)
        last_fed: Optional[float] = self.facts.get("terminal_sim")  # samples stamped before the result do not count
        diag = {"start_after": last_fed, "fed": 0, "max_gap": 0.0, "max_v": 0.0, "max_w": 0.0, "buffer_first": None,
                "buffer_last": None}
        while self.fsm.state is State.STOP_CONFIRM:
            self.rn.spin(0.05)
            buf = list(self.rn.odom)
            if buf:
                diag["buffer_first"], diag["buffer_last"] = buf[0][0], buf[-1][0]
            for t, v, w in buf:  # feed each odometry sample once, in stamp order
                if last_fed is None or t > last_fed:
                    if diag["fed"]:
                        diag["max_gap"] = max(diag["max_gap"], t - last_fed)
                    diag["fed"] += 1
                    diag["max_v"], diag["max_w"] = max(diag["max_v"], v), max(diag["max_w"], w)
                    last_fed = t
                    if tracker.update(t, v, w) is not None:
                        break
            if tracker.confirmed_at is not None:
                if not self.opts.no_sim:
                    gt = self.sim.entity_state(self.cfg.sim.robot_entity)
                    gt["sim_time_paired"] = self.rn.sim_time
                    g = self.scenario.goal
                    gt["error_to_goal_m"] = math.hypot(gt["x"] - g.x, gt["y"] - g.y)
                    self.facts["ground_truth"]["at_stop"] = gt
                    self.ev.write("ground_truth", **gt)
                self.facts["stop_confirmed_sim"] = tracker.confirmed_at
                self.go(State.TEARDOWN, f"robot at rest (stop-still confirmed at sim {tracker.confirmed_at:.3f})")
                return True
            to = self.fsm.check(*self.now())
            if to:
                self.ev.write("timeout", name=to, stop_still_diagnostics={**diag, "last_fed": last_fed})
                self.fsm.timeout(to, *self.now())
                self._sync()
                return False
        return False

    # ---- TEARDOWN ------------------------------------------------------------------------------------------------
    def _teardown(self) -> None:
        if self.fsm.state is not State.TEARDOWN:
            self.fsm.fail(f"teardown reached from {self.fsm.state.name}", *self.now())
        if self.transcript is not None:
            self.transcript.end(0)
        codes = self.facts["exit_codes"]
        if self._paused_by_injection:  # never leave the simulator paused
            self.ev.write("inject_resume", state=self.sim.set_state("playing"), reason="teardown")
            self._paused_by_injection = False
        if not self.opts.no_sim and "at_stop" not in self.facts["ground_truth"]:
            try:
                gt = self.sim.entity_state(self.cfg.sim.robot_entity)
                gt["sim_time_paired"] = self.rn.sim_time
                self.facts["ground_truth"]["at_end"] = gt
                self.ev.write("ground_truth_at_end", **gt)
            except Exception as exc:  # noqa: BLE001 - recorded; the verdict then has no ground truth
                self.ev.write("ground_truth_unavailable", error=str(exc))
        if self.facts["contacts"]["installed"]:
            try:
                got = contact_client.fetch()
                self.facts["contacts"].update(measured=True, events=got.get("events", []),
                                              found_pairs=contact_client.found_pairs(got),
                                              dropped=got.get("dropped", 0))
                self.ev.write("contacts_fetched", events=len(got.get("events", [])), dropped=got.get("dropped", 0))
            except contact_client.ContactError as exc:
                self.facts["contacts"].update(measured=False, error=str(exc))
                self.ev.write("contacts_unavailable", error=str(exc))
        if self.started["record"] and "stop_confirmed_sim" in self.facts:
            time.sleep(STOP_SETTLE_WALL_S)  # keep recording briefly so the offline analysis sees the whole rest window
        if self.started["record"]:
            codes["stop_record"] = script("stop_record.sh", [str(self.run_dir)], self.run_dir / "stop_record.txt", 180)
            self.ev.write("record_stop", exit_code=codes["stop_record"])
        if not self.opts.no_analyze and (self.run_dir / "rosbag").exists():
            g, s = self.scenario.goal, self.cfg.sim.spawn
            codes["analyze"] = script("analyze_attempt.sh", [str(self.run_dir), "--goal", str(g.x), str(g.y), str(g.yaw),
                                                             "--spawn", str(s.x), str(s.y), str(s.yaw)],
                                      self.run_dir / "analyze.txt", 300)
            self.ev.write("analyze", exit_code=codes["analyze"])
        if self.started["nav2"]:
            codes["stop_nav2"] = script("stop_nav2.sh", [str(self.run_dir)], self.run_dir / "stop_nav2.txt", 180)
            self.ev.write("nav2_stop", exit_code=codes["stop_nav2"])
        self.go(State.DONE, "teardown finished")
        self._write_result()  # last artifact: it includes the complete state history up to DONE

    def _write_result(self) -> None:
        path = self.run_dir / "result.json"
        result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "schema": "robosim-eval run result (D2 runner; no offline analysis)", "task_outcome": "unknown",
            "safety_status": "unknown", "data_status": "incomplete", "validation_status": "inconclusive"}
        keys = ("execution_status", "task_outcome", "safety_status", "data_status", "validation_status",
                "verdict_reasons", "arrival_check")
        result["analyzer"] = {k: result.get(k) for k in keys}  # D0 offline analysis, kept for comparison
        verdict, inputs = self._evaluate(result)
        result.update(execution_status=verdict.execution_status, task_outcome=verdict.task_outcome,
                      safety_status=verdict.safety_status, data_status=verdict.data_status,
                      validation_status=verdict.validation_status,
                      verdict_reasons={"fail": list(verdict.fail_reasons),
                                       "inconclusive": list(verdict.inconclusive_reasons),
                                       "warnings": list(verdict.warnings)})
        result["evaluator"] = verdict.to_dict()
        result["evaluator_inputs"] = to_plain(inputs)
        result["runner"] = {"run_id": self.run_dir.name, "scenario": self.scenario.name, "states": self.fsm.events(),
                            "errors": self.fsm.errors, "interrupted_by": self.fsm.interrupted_by,
                            "timeout_reason": self.fsm.timeout_reason, "abort_batch": self.fsm.abort_batch, **self.facts}
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        self.result = result

    def _evaluate(self, result: Dict[str, Any]):
        """D3 verdict from the runner facts, ground truth, contact data and the offline data-integrity check."""
        run, f = self.cfg.run, self.facts
        integ = result.get("data_integrity", {}) or {}

        def gap(name: str) -> Optional[float]:
            v = integ.get(name) or {}
            return v.get("max_wall_gap_s") if v.get("count") else None

        gt = f["ground_truth"].get("at_stop") or f["ground_truth"].get("at_end")
        term = f.get("terminal") or {}
        g = self.scenario.goal
        inputs = EvalInputs(
            scenario_expect=self.scenario.expect_outcome, preset_unreachable=self.scenario.preset_unreachable,
            tolerance_m=run.position_tolerance_m, goal=(g.x, g.y), execution_status=self.fsm.execution_status,
            runner_errors=tuple(self.fsm.errors), accepted=bool(f.get("goal_id")), rejected=bool(f.get("rejected")),
            terminal_status=term.get("status"), error_code=term.get("error_code"),
            cancel_requested=self.fsm.cancel_reason is not None, cancel_reason=self.fsm.cancel_reason,
            timeout_reason=self.fsm.timeout_reason, stop_confirmed="stop_confirmed_sim" in f,
            gt_at_stop=(gt["x"], gt["y"]) if gt else None, contacts_measured=bool(f["contacts"].get("measured")),
            contacts=tuple(tuple(p) for p in f["contacts"].get("found_pairs", [])),
            required_gaps={n: gap(n) for n in run.required_streams},
            required_backward={n: int((integ.get(n) or {}).get("backward_stamps", 0) or 0) for n in run.required_streams},
            informational_gaps={n: gap(n) for n in run.informational_streams},
            dropout_threshold_wall_s=run.dropout_wall_s, clock_backward_jumps=self.rn.clock_backward)
        policy = ContactPolicy(run.contact_robot_root, tuple(run.contact_ignore_prefixes))
        return evaluate_run(inputs, policy), inputs

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
    a = p.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except (OSError, ValueError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    if cfg.run is None or a.scenario not in cfg.scenarios:
        print(f"config has no run section or no scenario {a.scenario!r} (have: {sorted(cfg.scenarios)})", file=sys.stderr)
        return 2
    if a.no_sim:
        a.no_contacts = True  # contact data comes from inside Isaac
    if not a.no_sim and cfg.sim is None:
        print("config has no sim section (use --no-sim for the fake-node test)", file=sys.stderr)
        return 2
    run_dir = Path(a.out) / f"{a.scenario}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=False)
    print(f"run dir: {run_dir}", flush=True)
    runner = Runner(cfg, cfg.scenarios[a.scenario], run_dir, a)
    rc = runner.run()
    r = getattr(runner, "result", {})
    print(json.dumps({"run_dir": str(run_dir), "exit": rc, "execution_status": r.get("execution_status"),
                      "task_outcome": r.get("task_outcome"), "validation_status": r.get("validation_status"),
                      "errors": runner.fsm.errors}), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
