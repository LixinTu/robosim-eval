"""Fixed-input tests for the D2 run state machine (plan doc A5): transitions, per-state deadlines, final status."""
from __future__ import annotations

import pytest

from robosim_eval.runner_fsm import Limits, RunStateMachine, State, deadline_exceeded

LIM = Limits(ready_wall_s=60, accept_wall_s=10, nav_sim_s=120, nav_wall_s=300, cancel_wall_s=10, stop_wall_s=10)


def happy(fsm: RunStateMachine) -> None:
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.go(State.STOP_CONFIRM, 60.0, 22.0, "terminal status SUCCEEDED")
    fsm.go(State.TEARDOWN, 62.0, 23.0, "robot at rest")
    fsm.go(State.DONE, 70.0, 23.0, "teardown finished")


def test_happy_path_is_completed_and_keeps_the_history():
    fsm = RunStateMachine(LIM, 0.0, None)
    happy(fsm)
    assert fsm.state is State.DONE
    assert fsm.execution_status == "completed" and not fsm.abort_batch and fsm.timeout_reason is None
    assert [h.state for h in fsm.history] == [State.PREPARE, State.WAIT_READY, State.SEND_GOAL, State.EXECUTING,
                                              State.STOP_CONFIRM, State.TEARDOWN, State.DONE]
    assert fsm.history[3].t_sim == 12.4 and fsm.history[3].reason == "goal accepted"


def test_illegal_transition_is_refused():
    fsm = RunStateMachine(LIM, 0.0, None)
    with pytest.raises(ValueError, match="PREPARE -> EXECUTING"):
        fsm.go(State.EXECUTING, 1.0, None, "skip")


@pytest.mark.parametrize("state,entered,now,expected", [
    (State.WAIT_READY, (0.0, None), (60.5, None), "ready_timeout"),
    (State.WAIT_READY, (0.0, None), (59.0, None), None),
    (State.SEND_GOAL, (5.0, 1.0), (15.5, 1.1), "accept_timeout"),
    (State.EXECUTING, (10.0, 10.0), (200.0, 130.5), "nav_sim_timeout"),
    (State.EXECUTING, (10.0, 10.0), (310.5, 100.0), "nav_wall_timeout"),
    (State.EXECUTING, (10.0, 10.0), (100.0, 40.0), None),
    (State.CANCELING, (0.0, 0.0), (10.5, 3.0), "cancel_timeout"),
    (State.STOP_CONFIRM, (0.0, 0.0), (10.5, 3.0), "stop_timeout"),
    (State.TEARDOWN, (0.0, 0.0), (1e6, 1e6), None),
])
def test_per_state_deadlines(state, entered, now, expected):
    assert deadline_exceeded(state, entered[0], entered[1], now[0], now[1], LIM) == expected


def test_navigation_without_sim_time_uses_the_wall_cap_only():
    assert deadline_exceeded(State.EXECUTING, 0.0, None, 299.0, None, LIM) is None
    assert deadline_exceeded(State.EXECUTING, 0.0, None, 300.5, None, LIM) == "nav_wall_timeout"


def test_timeout_then_cancel_then_stop_is_completed_with_a_timeout_reason():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.timeout("nav_sim_timeout", 300.0, 132.5)
    assert fsm.state is State.CANCELING
    fsm.go(State.STOP_CONFIRM, 303.0, 133.0, "terminal status CANCELED")
    fsm.go(State.TEARDOWN, 305.0, 134.0, "robot at rest")
    fsm.go(State.DONE, 310.0, 134.0, "teardown finished")
    assert fsm.execution_status == "completed" and fsm.timeout_reason == "nav_sim_timeout"


def test_interrupt_during_execution_cancels_and_ends_interrupted():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.interrupt("SIGINT", 40.0, 15.0)
    assert fsm.state is State.CANCELING
    fsm.go(State.STOP_CONFIRM, 42.0, 15.5, "terminal status CANCELED")
    fsm.go(State.TEARDOWN, 44.0, 16.0, "robot at rest")
    fsm.go(State.DONE, 50.0, 16.0, "teardown finished")
    assert fsm.execution_status == "interrupted"


def test_interrupt_before_the_goal_goes_straight_to_teardown():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.interrupt("SIGTERM", 5.0, None)
    assert fsm.state is State.TEARDOWN
    fsm.go(State.DONE, 8.0, None, "teardown finished")
    assert fsm.execution_status == "interrupted"


def test_unconfirmed_stop_is_an_error_and_aborts_the_batch():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.go(State.STOP_CONFIRM, 60.0, 22.0, "terminal status ABORTED")
    fsm.timeout("stop_timeout", 70.5, 25.0)
    assert fsm.state is State.TEARDOWN
    fsm.go(State.DONE, 75.0, 25.0, "teardown finished")
    assert fsm.execution_status == "error" and fsm.abort_batch


def test_unconfirmed_cancel_is_an_error_and_aborts_the_batch():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.interrupt("SIGINT", 40.0, 15.0)
    fsm.timeout("cancel_timeout", 50.5, 18.0)
    assert fsm.state is State.TEARDOWN and fsm.abort_batch
    fsm.go(State.DONE, 55.0, 18.0, "teardown finished")
    assert fsm.execution_status == "error"


def test_ready_or_accept_timeout_is_an_error_without_aborting_the_batch():
    for state_path, reason in (([State.WAIT_READY], "ready_timeout"), ([State.WAIT_READY, State.SEND_GOAL], "accept_timeout")):
        fsm = RunStateMachine(LIM, 0.0, None)
        t = 1.0
        for st in state_path:
            fsm.go(st, t, None, "step")
            t += 1.0
        fsm.timeout(reason, 100.0, None)
        assert fsm.state is State.TEARDOWN
        fsm.go(State.DONE, 101.0, None, "teardown finished")
        assert fsm.execution_status == "error" and not fsm.abort_batch


def test_rejected_goal_goes_to_teardown_and_counts_as_completed():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.TEARDOWN, 31.0, 12.1, "goal rejected")
    fsm.go(State.DONE, 33.0, 12.1, "teardown finished")
    assert fsm.execution_status == "completed"


def test_failure_marks_error_and_moves_to_teardown():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.fail("reset-check failed: robot 0.3 m from the spawn", 5.0, None)
    assert fsm.state is State.TEARDOWN and fsm.execution_status == "error"
    assert "reset-check failed" in fsm.errors[0]


def test_history_serializes():
    fsm = RunStateMachine(LIM, 0.0, None)
    happy(fsm)
    rows = fsm.events()
    assert rows[0]["state"] == "PREPARE" and rows[-1]["state"] == "DONE" and "reason" in rows[1]
