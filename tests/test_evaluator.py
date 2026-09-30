"""Fixed-input tests for the D3 evaluator (plan doc A5): arrival, timeout, collision, cancel and unreachable are judged
separately from ground truth, contact data and data integrity. Includes the four mandatory bad-data cases."""
from __future__ import annotations

import dataclasses

from robosim_eval.evaluator import ContactPolicy, EvalInputs, evaluate_run

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


def test_preset_unreachable_goal_with_abort_is_unreachable_and_passes_its_scenario():
    v = run(scenario_expect="unreachable", preset_unreachable=True, terminal_status=6, error_code=208,
            gt_at_stop=(-6.0, -1.0), goal=(-10.05, -1.0))
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
