"""Runner flow tests without ROS (fakes in tests/test_runner_fakes.py): a sent goal is always resolved, the teardown
is exception-safe and its failures reach the exit code, injected pauses, and the D3 verdict plumbing (plan doc A5)."""
from __future__ import annotations

import json

import pytest

from robosim_eval.runner_fsm import State
from test_runner_fakes import FakeWorld, SimControlError, drive, events, finish, make_runner, sim_config, to_send_goal


def completed(r) -> None:
    """Goal sent, accepted, SUCCEEDED and the robot confirmed at rest: a normal run up to TEARDOWN."""
    to_send_goal(r)
    assert r._send_goal() and r._execute() and r.fsm.state is State.TEARDOWN


def raise_while_executing(r, after: float = 1.0) -> None:
    """An rclpy error while spinning, `after` s into EXECUTING (the runner-3 trigger)."""
    orig = r.rn.spin

    def spin(seconds: float = 0.05) -> None:
        orig(seconds)
        if r.fsm.state is State.EXECUTING and r.rn.world.t - r.fsm.entered.t_wall >= after:
            raise RuntimeError("rclpy error while spinning")
    r.rn.spin = spin


# ---- SEND_GOAL: a sent goal is never abandoned (runner-1, runner-7, runner-10) ---------------------------------------

def test_an_interrupt_before_the_goal_is_sent_leaves_no_goal(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch)
    to_send_goal(r)
    r.interrupt = "SIGINT"                       # e.g. during the recorder start
    assert r._send_goal() is False
    assert r.rn.nav.sent == [] and r.fsm.state is State.TEARDOWN and r.fsm.interrupted_by == "SIGINT"
    rc, res = finish(r)
    assert rc == 20 and "safety_net" not in res["runner"]


def test_an_interrupt_after_sending_waits_for_the_response_and_cancels(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(response_delay=1.0))
    to_send_goal(r)
    orig = r.rn.spin

    def spin(seconds: float = 0.05) -> None:   # SIGINT arrives while the goal response is outstanding
        orig(seconds)
        if w.sent_at is not None and r.interrupt is None:
            r.interrupt = "SIGINT"
    r.rn.spin = spin
    drive(r, r._send_goal, r._execute)
    rc, res = finish(r)
    assert rc == 20 and res["execution_status"] == "interrupted"
    assert res["runner"]["terminal"]["name"] == "CANCELED" and w.cancel_requests >= 1
    assert "stop_confirmed_sim" in res["runner"] and not res["runner"]["abort_batch"]


def test_the_acceptance_wait_starts_when_the_goal_is_sent(tmp_path, monkeypatch):
    # runner-7: the recorder start takes 4 s of SEND_GOAL; the acceptance itself 3 s (accept_wall_s 5)
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(response_delay=3.0, finish_after=1.0),
                                no_record=False)
    scripts.effects["record_d0.sh"] = lambda d: ((d / "record.pids").write_text("bag 1\n"), w.advance(4.0))
    to_send_goal(r)
    assert r._send_goal() is True and r.fsm.state is State.EXECUTING
    assert [e["reason"] for e in events(r) if e["event"] == "state"][-2].startswith("goal ")


def test_a_late_acceptance_is_canceled_by_the_safety_net(tmp_path, monkeypatch):
    # runner-1 case B: accept_timeout (5 s) fires, the goal response comes 2 s later: cancel it, confirm the stop
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(response_delay=7.0))
    to_send_goal(r)
    assert r._send_goal() is False and r.fsm.errors == ["accept_timeout"]
    rc, res = finish(r)
    assert rc == 30 and not res["runner"]["abort_batch"]
    assert res["runner"]["safety_net"] == {"cancel": "confirmed", "stop": "confirmed"}
    assert res["runner"]["terminal"]["name"] == "CANCELED" and res["runner"]["goal_id"]


def test_a_goal_without_any_response_aborts_the_batch(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(response_delay=None))
    to_send_goal(r)
    assert r._send_goal() is False
    rc, res = finish(r)
    assert rc == 31 and res["runner"]["abort_batch"] and r.rn.raw_cancels >= 1
    assert res["runner"]["safety_net"] == {"cancel": "not confirmed"}
    # runner-10: no terminal result was received, so the transcript does not claim a client exit 0
    transcript = next(r.run_dir.glob("goal-*.txt")).read_text(encoding="utf-8").splitlines()
    assert transcript[-1].split("action_client_exit=")[1].startswith("none")


def test_an_accepted_goal_whose_response_was_lost_is_canceled_by_id(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(response_delay=0.5, response_lost=True))
    to_send_goal(r)
    assert r._send_goal() is False
    rc, res = finish(r)
    assert rc == 30 and res["runner"]["terminal"]["name"] == "CANCELED"
    assert res["runner"]["terminal"]["source"] == "safety net (get_result by goal id)"
    assert res["runner"]["safety_net"]["stop"] == "confirmed"


# ---- internal errors after acceptance (runner-3) -------------------------------------------------------------------

def test_an_internal_error_while_executing_cancels_and_confirms_the_stop(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch)
    to_send_goal(r)
    raise_while_executing(r)
    drive(r, r._send_goal, r._execute)
    rc, res = finish(r)
    assert rc == 30 and any("internal error" in e for e in res["runner"]["errors"])
    assert res["runner"]["terminal"]["name"] == "CANCELED" and w.cancel_requests == 1
    assert res["runner"]["safety_net"] == {"cancel": "confirmed", "stop": "confirmed"}


def test_an_internal_error_with_an_ignored_cancel_aborts_the_batch(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(cancel_honoured=False))
    to_send_goal(r)
    raise_while_executing(r)
    drive(r, r._send_goal, r._execute)
    rc, res = finish(r)
    assert rc == 31 and res["runner"]["abort_batch"] and "terminal" not in res["runner"]


def test_an_internal_error_while_confirming_the_stop_is_confirmed_by_the_safety_net(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0))
    to_send_goal(r)
    r._confirm_stop = lambda: (_ for _ in ()).throw(RuntimeError("odometry callback failed"))
    drive(r, r._send_goal, r._execute)
    rc, res = finish(r)
    assert rc == 30 and res["runner"]["safety_net"] == {"stop": "confirmed"}


# ---- TEARDOWN: every step runs, failures reach the exit code (runner-4, critic-2, runner-8) -------------------------

def test_a_failing_teardown_step_does_not_skip_the_others(tmp_path, monkeypatch):
    r, w, scripts = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path), no_sim=False, no_nav2=False,
                                no_record=False, no_analyze=False)
    r.started.update(record=True, nav2=True)
    r._paused_by_injection, r.sim.state = True, "paused"
    r.sim.fail["set_state"] = SimControlError("/set_simulation_state: no response within 15.0 s")
    scripts.raises["stop_record.sh"] = OSError("cannot open stop_record.txt")
    (r.run_dir / "rosbag").mkdir()
    r.fsm.fail("internal error: boom", *r.now())
    rc, res = finish(r)
    assert scripts.names() == ["stop_record.sh", "analyze_attempt.sh", "stop_nav2.sh"]
    assert res["runner"]["states"][-1]["state"] == "DONE" and rc == 31
    assert any(e.startswith("teardown step resume failed") for e in res["runner"]["errors"])
    assert any(e.startswith("teardown step stop_record failed") for e in res["runner"]["errors"])
    assert [e["step"] for e in events(r) if e["event"] == "teardown_error"] == ["resume", "stop_record"]


@pytest.mark.parametrize("name,code", [("stop_nav2.sh", 1), ("stop_nav2.sh", 5), ("stop_nav2.sh", 124),
                                       ("stop_record.sh", 3), ("stop_record.sh", 124)])
def test_resident_processes_not_confirmed_stopped_abort_the_batch(tmp_path, monkeypatch, name, code):
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0), no_nav2=False,
                                no_record=False)
    r.started.update(record=True, nav2=True)
    scripts.codes[name] = code
    completed(r)
    rc, res = finish(r)
    assert rc == 31 and res["execution_status"] == "error" and res["runner"]["abort_batch"]
    assert any(f"{name} exit {code}" in e for e in res["runner"]["errors"])


def test_a_recording_problem_at_stop_record_is_incomplete_data_not_an_error(tmp_path, monkeypatch):
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0), no_record=False,
                                no_analyze=False)
    r.started["record"] = True
    scripts.codes["stop_record.sh"] = 6
    completed(r)
    rc, res = finish(r)
    assert res["execution_status"] == "completed" and res["data_status"] == "incomplete"
    assert any("stop_record.sh exit 6" in s for s in res["verdict_reasons"]["inconclusive"])


def test_a_failed_offline_analysis_is_reported_as_such(tmp_path, monkeypatch):
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0), no_record=False,
                                no_analyze=False)
    r.started["record"] = True
    scripts.codes["analyze_attempt.sh"] = 2
    scripts.effects["stop_record.sh"] = lambda d: (d / "rosbag").mkdir()
    completed(r)
    rc, res = finish(r)
    reasons = " ".join(res["verdict_reasons"]["inconclusive"])
    assert "offline analysis failed (analyze_attempt.sh exit 2" in reasons and "no data" not in reasons
    assert res["analyzer"] is None and res["data_status"] == "incomplete"


def test_partially_started_recorders_and_nav2_are_stopped(tmp_path, monkeypatch):
    # runner-8: record_d0.sh exit 1 with some recorders running; start_nav2.sh exit 4 with its wrapper alive
    r, w, scripts = make_runner(tmp_path, monkeypatch, no_record=False)
    scripts.codes["record_d0.sh"] = 1
    scripts.effects["record_d0.sh"] = lambda d: (d / "record.pids").write_text("bag 4242\nodom MISSING\n")
    to_send_goal(r)
    assert r._send_goal() is False
    finish(r)
    assert "stop_record.sh" in scripts.names()
    r2, w2, scripts2 = make_runner(tmp_path / "b", monkeypatch, no_nav2=False)
    scripts2.codes["start_nav2.sh"] = 4
    scripts2.effects["start_nav2.sh"] = lambda d: (d / "nav2.pid").write_text("4343\n")
    r2.fsm.go(State.WAIT_READY, w2.t, None, "prepared")
    assert r2._wait_ready() is False
    rc, _ = finish(r2)
    assert "stop_nav2.sh" in scripts2.names() and rc == 30


def test_start_nav2_refused_because_another_nav2_runs_aborts_the_batch(tmp_path, monkeypatch):
    r, w, scripts = make_runner(tmp_path, monkeypatch, no_nav2=False)
    scripts.codes["start_nav2.sh"] = 3
    scripts.effects["start_nav2.sh"] = lambda d: None   # refused before anything was started (no nav2.pid)
    r.fsm.go(State.WAIT_READY, w.t, None, "prepared")
    assert r._wait_ready() is False
    rc, _ = finish(r)
    assert rc == 31 and "stop_nav2.sh" not in scripts.names()


# ---- injected pause (runner-5, runner-6) ----------------------------------------------------------------------------

def test_a_pause_whose_reply_failed_is_resumed_at_teardown(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path), scenario="pause", no_sim=False)
    r.sim.apply_then_fail["paused"] = SimControlError("/get_simulation_state: no response within 15.0 s")
    to_send_goal(r)
    drive(r, r._send_goal, r._execute)
    assert r.sim.state == "paused" and r.fsm.state is State.TEARDOWN
    rc, res = finish(r)
    assert r.sim.state == "playing" and "set_state(playing)" in r.sim.calls
    assert [e for e in events(r) if e["event"] == "inject_pause_request"]
    assert rc == 30 and res["runner"]["terminal"]["name"] == "CANCELED"


def test_a_terminal_status_during_an_injected_pause_is_not_a_stop_timeout(tmp_path, monkeypatch):
    # the goal finishes (on wall time) 1 s into a 6 s pause; odometry resumes only with the simulation
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=2.0), cfg_path=sim_config(tmp_path),
                          scenario="pause", no_sim=False)
    to_send_goal(r)
    drive(r, r._send_goal, r._execute)
    rc, res = finish(r)
    assert "stop_timeout" not in res["runner"]["errors"] and not res["runner"]["abort_batch"]
    assert res["runner"]["terminal"]["name"] == "SUCCEEDED" and "stop_confirmed_sim" in res["runner"]
    kinds = [i["kind"] for i in res["runner"]["injections"]]
    assert kinds == ["pause", "resume"]
    resumed = [e for e in events(r) if e["event"] == "state" and e["reason"].startswith("simulation resumed")]
    assert resumed and resumed[0]["state"] == "STOP_CONFIRM"


def test_the_pause_starts_only_while_executing(tmp_path, monkeypatch):
    # an interrupt right after acceptance; Nav2 takes 3 s to acknowledge the cancel, and the pause falls due meanwhile
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(cancel_delay=3.0), cfg_path=sim_config(tmp_path),
                          scenario="pause", no_sim=False)
    to_send_goal(r)
    assert r._send_goal()
    r.interrupt = "SIGINT"
    drive(r, r._execute)
    rc, res = finish(r)
    assert "set_state(paused)" not in r.sim.calls and res["runner"]["terminal"]["name"] == "CANCELED" and rc == 20


# ---- D3 verdict plumbing and result.json layout (eval-1, eval-12, C8, runner-9) -------------------------------------

def analysis(first=5.0, last=40.0, in_window=100, backward=0, **coverage):
    streams = ("clock", "odom", "tf_odom_base", "tf_map_odom")
    return {"schema": "robosim-eval attempt result, D0 (plan doc A5)", "execution_status": "completed",
            "task_outcome": "reached", "safety_status": "unknown", "data_status": "complete",
            "validation_status": "pass", "verdict_reasons": {"fail": [], "inconclusive": []},
            "arrival_check": {"error_to_goal_m": 0.1, "tolerance_m": 0.5}, "positions": {}, "stop_still": {},
            "notes": ["safety_status is unknown: contact/collision was not measured in D0 (D3)."],
            "timing": {"accept_to_result_sim_s": 12.0}, "nav2_raw": {"terminal_status_name": "SUCCEEDED"},
            "goal": {"x": 1.0, "y": 0.0}, "target_goal": {"id": "01" * 16},
            "data_integrity": {n: {"count": 500, "count_in_window": in_window, "max_wall_gap_s": 0.3,
                                   "backward_stamps": backward} for n in streams},
            "coverage": {"target_goal_observed": True, "accepted_recorded": True, "terminal_recorded": True,
                         "streams": {n: {"first_sim_s": first, "last_sim_s": last} for n in streams}, **coverage}}


def analysed_run(tmp_path, monkeypatch, result, bag_exit=None):
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0), no_record=False,
                                no_analyze=False)
    r.started["record"] = True
    scripts.codes["analyze_attempt.sh"] = 11

    def stop_record(d):
        (d / "rosbag").mkdir()
        if bag_exit is not None:
            (d / "bag.exit").write_text(f"{bag_exit}\n")
    scripts.effects["stop_record.sh"] = stop_record
    scripts.effects["analyze_attempt.sh"] = lambda d: (d / "result.json").write_text(json.dumps(result))
    completed(r)
    rc, res = finish(r)
    return r, scripts, res


def test_result_json_keeps_the_verdict_at_the_top_and_the_analyzer_below(tmp_path, monkeypatch):
    r, scripts, res = analysed_run(tmp_path, monkeypatch, analysis(first=5.0, last=1e6))
    for key in ("execution_status", "task_outcome", "safety_status", "data_status", "validation_status",
                "verdict_reasons", "evaluator", "evaluator_inputs", "runner", "timing", "nav2_raw", "data_integrity",
                "goal", "target_goal"):
        assert key in res, key
    for key in ("arrival_check", "positions", "notes", "stop_still", "coverage"):
        assert key not in res and key in res["analyzer"], key
    assert res["analyzer"]["validation_status"] == "pass" and res["schema"].startswith("robosim-eval run result")
    assert res["data_status"] == "complete" and res["timing"] == {"accept_to_result_sim_s": 12.0}
    args = dict(zip(*[iter(next(a for n, a in scripts.calls if n == "analyze_attempt.sh")[1:])] * 2))
    assert args["--tolerance"] == "0.5" and args["--dropout"] == "2.0" and args["--max-stop-gap"] == "0.25"


def test_a_recording_that_ends_before_the_run_makes_the_data_incomplete(tmp_path, monkeypatch):
    # eval-1: the bag's own window ends where the bag ends, so only the runner's times reveal the truncation
    r, _, res = analysed_run(tmp_path, monkeypatch, analysis(first=5.0, last=11.0))
    assert res["data_status"] == "incomplete"
    assert any("the recording ends at sim 11.00 s" in s for s in res["verdict_reasons"]["inconclusive"])


@pytest.mark.parametrize("change,words", [(dict(in_window=0), "clock: no data"),
                                          (dict(backward=3), "odom: 3 backward stamps"),
                                          (dict(accepted_recorded=False), "ACCEPTED/EXECUTING"),
                                          (dict(terminal_recorded=False), "terminal status was not recorded")])
def test_analyzer_findings_reach_the_verdict(tmp_path, monkeypatch, change, words):
    r, _, res = analysed_run(tmp_path, monkeypatch, analysis(last=1e6, **change))
    assert res["data_status"] == "incomplete" and words in " ".join(res["verdict_reasons"]["inconclusive"])


def test_a_bag_recorder_at_its_time_cap_makes_the_data_incomplete(tmp_path, monkeypatch):
    r, _, res = analysed_run(tmp_path, monkeypatch, analysis(last=1e6), bag_exit=124)
    assert res["data_status"] == "incomplete" and "time cap" in " ".join(res["verdict_reasons"]["inconclusive"])


def test_lost_contact_events_reach_the_safety_verdict(tmp_path, monkeypatch):
    # runner-9, simctl-2: the monitor's dropped count goes to the evaluator (contracts C1, C4)
    r, w, _ = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0))
    completed(r)
    r.facts["contacts"].update(installed=True, measured=True, found_pairs=[], dropped=1200)
    r.facts["contacts"]["installed"] = False   # already fetched: the teardown does not fetch again
    rc, res = finish(r)
    assert res["safety_status"] == "unknown" and res["evaluator_inputs"]["contacts_dropped"] == 1200
