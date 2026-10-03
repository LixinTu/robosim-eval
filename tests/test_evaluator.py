"""Fixed-input tests for the D3 evaluator (plan doc A5): arrival, timeout, collision, cancel and unreachable are judged
separately from ground truth, contact data and data integrity. Includes the four mandatory bad-data cases."""
from __future__ import annotations

import dataclasses

from robosim_eval.evaluator import ContactPolicy, EvalInputs, evaluate_run, integrity_gap, recording_coverage_problems

ROBOT = "/World/Nova_Carter_ROS"
GROUND = ("/World/warehouse_with_forklifts/GroundPlane/",
          "/World/warehouse_with_forklifts/Warehouse_Empty_small_realtime/GroundPlane/")
POLICY = ContactPolicy(robot_root=ROBOT, ignore_prefixes=GROUND)
GROUND_CONTACT = (f"{ROBOT}/wheel_left", "/World/warehouse_with_forklifts/GroundPlane/collisionPlane")

BASE = EvalInputs(
    scenario_expect="reached", preset_unreachable=False, tolerance_m=0.5, goal=(0.0, -1.0),
    execution_status="completed", runner_errors=(), accepted=True, rejected=False, terminal_status=4, error_code=0,
    cancel_requested=False, cancel_reason=None, timeout_reason=None, stop_confirmed=True, gt_at_stop=(-0.25, -0.93),
    contacts_measured=True, contacts=(GROUND_CONTACT,), required_gaps={"clock": 1.2, "odom": 1.2, "tf_odom_base": 1.2},
    required_backward={"clock": 0, "odom": 0, "tf_odom_base": 0}, informational_gaps={"tf_map_odom": 2.5},
    dropout_threshold_wall_s=2.0, clock_backward_jumps=0)


def run(**changes):
    return evaluate_run(dataclasses.replace(BASE, **changes), POLICY)


def test_normal_arrival_with_ground_contacts_only_passes():
    v = run()
    assert (v.execution_status, v.task_outcome, v.safety_status, v.data_status, v.validation_status) == \
        ("completed", "reached", "pass", "complete", "pass")
    assert abs(v.arrival_error_m - 0.2596) < 1e-3


def test_informational_amcl_gap_is_only_a_warning():
    v = run()
    assert v.data_status == "complete" and any("tf_map_odom" in w for w in v.warnings)


def test_bad_data_false_success_is_not_a_pass():
    v = run(gt_at_stop=(-1.2, -1.0))  # Nav2 says SUCCEEDED, ground truth 1.2 m from the goal
    assert v.task_outcome == "unknown" and v.validation_status == "fail"
    assert any("false success" in r for r in v.fail_reasons)


def test_bad_data_missing_contact_data_is_not_a_pass():
    v = run(contacts_measured=False, contacts=())
    assert v.safety_status == "unknown" and v.validation_status == "inconclusive"
    assert any("contact" in r for r in v.inconclusive_reasons)


def test_bad_data_time_going_backwards_is_not_a_pass():
    v = run(clock_backward_jumps=1)
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"


def test_bad_data_cancel_without_acknowledgement_is_not_a_pass():
    v = run(cancel_requested=True, cancel_reason="interrupt", terminal_status=None, stop_confirmed=False,
            execution_status="error", runner_errors=("cancel_timeout",))
    assert v.execution_status == "error" and v.validation_status == "fail"
    assert any("acknowledg" in r for r in v.fail_reasons)


def test_collision_with_an_obstacle_fails_safety():
    hit = (f"{ROBOT}/chassis_link", "/World/RoboSimObstacles/low_box/Geom")
    v = run(contacts=(GROUND_CONTACT, hit))
    assert v.safety_status == "fail" and v.validation_status == "fail"
    assert v.disallowed_contacts == (hit,)


def test_robot_self_contacts_are_ignored():
    v = run(contacts=((f"{ROBOT}/wheel_left", f"{ROBOT}/chassis_link"),))
    assert v.safety_status == "pass"


def test_stop_not_confirmed_after_success_fails():
    v = run(stop_confirmed=False)
    assert v.task_outcome == "unknown" and v.validation_status == "fail"


def test_required_stream_gap_makes_data_incomplete():
    v = run(required_gaps={"clock": 4.0, "odom": 4.0, "tf_odom_base": 4.0})
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"


def test_missing_required_stream_makes_data_incomplete():
    v = run(required_gaps={"clock": 1.0, "odom": None, "tf_odom_base": 1.0})
    assert v.data_status == "incomplete"


UNREACHABLE = dict(scenario_expect="unreachable", preset_unreachable=True, terminal_status=6, error_code=208,
                   gt_at_stop=(-6.0, -1.0), goal=(-10.05, -1.0), unreachable_evidence=True)


def test_preset_unreachable_goal_with_abort_is_unreachable_and_passes_its_scenario():
    v = run(**UNREACHABLE)
    assert v.task_outcome == "unreachable" and v.validation_status == "pass"


def test_abort_without_a_preset_label_stays_unknown_and_fails_a_reach_scenario():
    v = run(terminal_status=6, error_code=208, gt_at_stop=(-6.0, -1.0))
    assert v.task_outcome == "unknown" and v.validation_status == "fail"
    assert any("208" in r for r in v.fail_reasons)


def test_timeout_is_judged_separately():
    v = run(scenario_expect="timeout", timeout_reason="nav_sim_timeout", cancel_requested=True,
            cancel_reason="nav_sim_timeout", terminal_status=5, gt_at_stop=(-3.0, -1.0))
    assert v.task_outcome == "timeout" and v.validation_status == "pass"


def test_timeout_in_a_reach_scenario_fails():
    v = run(timeout_reason="nav_wall_timeout", cancel_requested=True, cancel_reason="nav_wall_timeout", terminal_status=5)
    assert v.task_outcome == "timeout" and v.validation_status == "fail"


def test_injected_cancel_is_canceled_and_passes_its_scenario():
    v = run(scenario_expect="canceled", cancel_requested=True, cancel_reason="injected", terminal_status=5,
            gt_at_stop=(-4.0, -1.0))
    assert v.task_outcome == "canceled" and v.validation_status == "pass"


def test_interrupted_run_is_never_a_pass():
    v = run(execution_status="interrupted", cancel_requested=True, cancel_reason="interrupt", terminal_status=5)
    assert v.validation_status == "inconclusive"


def test_rejected_goal_is_unknown():
    v = run(accepted=False, rejected=True, terminal_status=None, stop_confirmed=False)
    assert v.task_outcome == "unknown" and v.validation_status == "fail"


def test_verdict_serializes():
    import json
    assert '"validation_status": "pass"' in json.dumps(run().to_dict())


def test_integrity_gap_needs_messages_inside_the_window():
    # The D3 verdict takes the analyzer's data_integrity entries; a stream with messages only outside the
    # accept..arrival window has no usable gap (it counts as "no data"), whatever its whole-recording count.
    assert integrity_gap({"count": 5, "count_in_window": 0, "max_wall_gap_s": 1.5}) is None
    assert integrity_gap({"count": 5, "count_in_window": 3, "max_wall_gap_s": 1.5}) == 1.5
    assert integrity_gap({}) is None and integrity_gap(None) is None


# ---- review round 2 (eval-1, eval-6..eval-11, runner-9, simctl-2, doctor_config-10) -------------------------------
# Every test takes no arguments: artifacts/d3/mutation_check.py calls them directly against in-memory mutants.

def test_abort_without_a_preset_label_is_never_unreachable():
    v = run(**{**UNREACHABLE, "preset_unreachable": False})   # map evidence and a no-path code, but no preset label
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"


def test_unreachable_needs_complete_data():
    v = run(**{**UNREACHABLE, "required_gaps": {"clock": 4.0, "odom": 1.0, "tf_odom_base": 1.0}})
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"


def test_abort_with_ground_truth_at_the_goal_is_not_unreachable():
    v = run(**{**UNREACHABLE, "gt_at_stop": (-10.0, -1.0)})
    assert v.task_outcome == "unknown" and v.validation_status == "fail"
    assert any("reached the goal" in r for r in v.fail_reasons)


def test_required_backward_stamps_make_data_incomplete():
    v = run(required_backward={"clock": 0, "odom": 2, "tf_odom_base": 0})
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"
    assert any("odom: 2 backward stamps" in r for r in v.inconclusive_reasons)


def test_canceled_status_without_a_cancel_request_is_unknown():
    v = run(scenario_expect="canceled", terminal_status=5)   # Nav2 canceled, but the runner never asked for it
    assert v.task_outcome == "unknown" and v.validation_status != "pass"


def test_unreachable_needs_a_no_path_error_code():
    # ComputePathToPose (nav2_msgs, Jazzy): 201 INVALID_PLANNER, 202 TF_ERROR, 204 GOAL_OUTSIDE_MAP; FollowPath 105
    for code in (201, 202, 204, 105, None):
        v = run(**{**UNREACHABLE, "error_code": code})
        assert v.task_outcome == "unknown" and v.validation_status == "inconclusive", code
        assert any("error_code" in r for r in v.inconclusive_reasons), code
    assert run(**{**UNREACHABLE, "error_code": 207}).task_outcome == "unreachable"   # planner TIMEOUT


def test_rejected_preset_unreachable_goal_stays_unknown():
    v = run(**{**UNREACHABLE, "terminal_status": None, "rejected": True, "accepted": False, "error_code": None,
               "stop_confirmed": False})
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"


def test_unreachable_needs_map_evidence():
    for evidence in (None, False):
        v = run(**{**UNREACHABLE, "unreachable_evidence": evidence})
        assert v.task_outcome == "unknown" and v.validation_status == "inconclusive", evidence
        assert any("map" in r for r in v.inconclusive_reasons), evidence


def test_unreachable_without_ground_truth_is_unknown():
    v = run(**{**UNREACHABLE, "gt_at_stop": None})
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"
    assert any("ground truth" in r for r in v.inconclusive_reasons)


def test_canceled_timeout_and_unreachable_need_the_robot_at_rest():
    cases = (dict(scenario_expect="canceled", cancel_requested=True, cancel_reason="injected", terminal_status=5),
             dict(scenario_expect="timeout", timeout_reason="nav_sim_timeout", cancel_requested=True,
                  cancel_reason="nav_sim_timeout", terminal_status=5),
             UNREACHABLE)
    for case in cases:
        v = run(**{**case, "stop_confirmed": False})
        assert v.validation_status == "fail", case
        assert any("not confirmed at rest" in r for r in v.fail_reasons), case


def test_lost_contact_events_make_safety_unknown():
    v = run(contacts_dropped=1200)
    assert v.safety_status == "unknown" and v.validation_status == "inconclusive"
    assert any("lost" in r for r in v.inconclusive_reasons)


def test_lost_contact_events_do_not_hide_an_observed_collision():
    hit = (f"{ROBOT}/chassis_link", "/World/RoboSimObstacles/low_box/Geom")
    v = run(contacts=(GROUND_CONTACT, hit), contacts_dropped=3)
    assert v.safety_status == "fail" and v.validation_status == "fail"


def test_non_finite_ground_truth_is_not_a_pass():
    nan = float("nan")
    v = run(gt_at_stop=(nan, -1.0))
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"
    v = run(**{**UNREACHABLE, "gt_at_stop": (nan, nan)})
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"
    v = run(goal=(float("inf"), -1.0))
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"


def test_non_finite_tolerance_is_not_a_pass():
    v = run(gt_at_stop=(-5.0, -1.0), tolerance_m=float("nan"))
    assert v.task_outcome == "unknown" and v.validation_status == "inconclusive"
    assert any("tolerance" in r for r in v.inconclusive_reasons)


def test_non_finite_gap_or_threshold_makes_data_incomplete():
    v = run(required_gaps={"clock": float("nan"), "odom": 1.0, "tf_odom_base": 1.0})
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"
    v = run(dropout_threshold_wall_s=float("nan"))
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"


def test_recording_coverage_problems_make_data_incomplete():
    v = run(coverage_problems=("odom: the recording ends at sim 3.00 s, before the run ended (12.00 s)",))
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"
    assert any("recording ends" in r for r in v.inconclusive_reasons)


def test_no_checked_required_stream_is_not_complete_data():
    v = run(required_gaps={}, required_backward={})
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"


def test_expected_collision_passes_its_fault_injection_scenario():
    hit = (f"{ROBOT}/wheel_left", "/World/RoboSimObstacles/low_box/Geom")
    v = run(contacts=(GROUND_CONTACT, hit), scenario_expect_safety="fail")
    assert v.safety_status == "fail" and v.validation_status == "pass"
    assert not v.fail_reasons and any("expected by the scenario" in w for w in v.warnings)


def test_undetected_expected_collision_fails_its_scenario():
    v = run(scenario_expect_safety="fail")   # ground contacts only: the injected collision was not detected
    assert v.safety_status == "pass" and v.validation_status == "fail"
    v = run(scenario_expect_safety="fail", contacts_measured=False, contacts=())
    assert v.safety_status == "unknown" and v.validation_status == "inconclusive"


def test_expected_dropout_passes_its_fault_injection_scenario():
    v = run(required_gaps={"clock": 6.1, "odom": 6.1, "tf_odom_base": 6.1}, scenario_expect_data="incomplete")
    assert v.data_status == "incomplete" and v.validation_status == "pass"


def test_undetected_expected_dropout_fails_its_scenario():
    v = run(scenario_expect_data="incomplete")   # gaps of 1.2 s: the injected pause did not show in the data
    assert v.data_status == "complete" and v.validation_status == "fail"


def test_expected_dropout_does_not_cover_other_missing_data():
    v = run(required_gaps={"clock": 6.1, "odom": None, "tf_odom_base": 6.1}, scenario_expect_data="incomplete")
    assert v.data_status == "incomplete" and v.validation_status == "inconclusive"


COVERED = {"target_goal_observed": True, "accepted_recorded": True, "terminal_recorded": True,
           "streams": {n: {"first_sim_s": 1.0, "last_sim_s": 30.0} for n in ("clock", "odom", "tf_odom_base")}}
STREAMS = ("clock", "odom", "tf_odom_base")


def coverage(cov=None, start=5.0, end=25.0, accepted=True, terminal=True):
    return recording_coverage_problems(COVERED if cov is None else cov, start, end, accepted, terminal, STREAMS, 0.25)


def test_a_recording_that_spans_the_run_has_no_coverage_problem():
    assert coverage() == []


def test_a_recording_that_ends_before_the_run_is_a_coverage_problem():
    # eval-1: the analyzer's window comes from the bag, so a bag cut at sim 12 s has no gap of its own
    cut = {**COVERED, "streams": {**COVERED["streams"], "odom": {"first_sim_s": 1.0, "last_sim_s": 12.0}}}
    out = coverage(cut)
    assert len(out) == 1 and "odom: the recording ends at sim 12.00 s" in out[0]


def test_a_recording_that_starts_after_the_acceptance_is_a_coverage_problem():
    late = {**COVERED, "streams": {**COVERED["streams"], "clock": {"first_sim_s": 9.0, "last_sim_s": 30.0}}}
    assert any("clock: the recording starts" in p for p in coverage(late))


def test_goal_status_missing_from_the_recording_is_a_coverage_problem():
    assert any("not observed" in p for p in coverage({**COVERED, "target_goal_observed": False}))
    assert any("ACCEPTED/EXECUTING" in p for p in coverage({**COVERED, "accepted_recorded": False}))
    assert any("terminal status" in p for p in coverage({**COVERED, "terminal_recorded": False}))
    assert coverage({**COVERED, "target_goal_observed": False, "accepted_recorded": False}, accepted=False,
                    terminal=False, start=None, end=None) == []   # a rejected goal never appears in the status topic


def test_missing_coverage_or_stream_is_a_coverage_problem():
    assert recording_coverage_problems(None, 5.0, 25.0, True, True, STREAMS, 0.25) == [
        "the offline analysis reported no recording coverage"]
    assert any("tf_odom_base: no samples" in p
               for p in coverage({**COVERED, "streams": {k: v for k, v in COVERED["streams"].items() if k != "tf_odom_base"}}))
