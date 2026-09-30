"""Fixed-input tests for the D2 run state machine (plan doc A5): transitions, per-state deadlines, final status."""
from __future__ import annotations

import pytest

from robosim_eval.runner_fsm import Limits, RunStateMachine, State, deadline_exceeded, refresh_clock

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


def feed(tracker, samples):
    out = None
    for t, v, w in samples:
        out = tracker.update(t, v, w)
    return out


def test_stop_still_confirms_after_the_hold_time_at_rest():
    from robosim_eval.runner_fsm import StopStillTracker
    tr = StopStillTracker(linear=0.05, angular=0.1, hold_s=1.0, max_gap_s=0.25)
    assert feed(tr, [(10.0 + i * 0.05, 0.01, 0.02) for i in range(20)]) is None  # 0.95 s so far
    assert tr.update(11.0, 0.01, 0.02) == 11.0 and tr.confirmed_at == 11.0


def test_stop_still_restarts_on_motion_gap_or_backward_stamp():
    from robosim_eval.runner_fsm import StopStillTracker
    tr = StopStillTracker(linear=0.05, angular=0.1, hold_s=1.0, max_gap_s=0.25)
    feed(tr, [(10.0 + i * 0.05, 0.0, 0.0) for i in range(15)])      # 0.7 s at rest
    tr.update(10.75, 0.3, 0.0)                                      # moving again
    assert feed(tr, [(10.8 + i * 0.05, 0.0, 0.0) for i in range(20)]) is None   # 0.95 s since restart
    assert tr.update(12.1, 0.0, 0.0) is None                        # gap 0.35 s > max_gap: restart at 12.1
    assert tr.update(12.0, 0.0, 0.0) is None                        # backward stamp: restart at 12.0
    assert tr.confirmed_at is None
    assert feed(tr, [(12.0 + i * 0.05, 0.0, 0.0) for i in range(1, 21)]) == pytest.approx(13.0)


def test_stop_still_allows_a_gap_equal_to_the_maximum():
    from robosim_eval.runner_fsm import StopStillTracker
    tr = StopStillTracker(linear=0.05, angular=0.1, hold_s=1.0, max_gap_s=0.25)
    feed(tr, [(10.0, 0.0, 0.0), (10.25, 0.0, 0.0), (10.5, 0.0, 0.0), (10.75, 0.0, 0.0)])
    assert tr.update(11.0, 0.0, 0.0) == 11.0


def test_doctor_retry_only_for_degraded_data_and_bounded():
    from robosim_eval.runner_fsm import doctor_retry
    assert doctor_retry(12, attempt=1, max_attempts=3) is True     # lidar irregular for a few seconds after a reset
    assert doctor_retry(12, attempt=3, max_attempts=3) is False    # bounded
    for rc in (0, 10, 11, 13, 2, 124):                              # healthy, or structural problems: never retried
        assert doctor_retry(rc, attempt=1, max_attempts=3) is False


def test_injected_cancel_is_not_an_operator_interrupt():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.cancel("injected cancel at sim 17.4", 40.0, 17.4)
    assert fsm.state is State.CANCELING and fsm.cancel_reason == "injected"
    fsm.go(State.STOP_CONFIRM, 41.0, 17.6, "terminal status CANCELED")
    fsm.go(State.TEARDOWN, 43.0, 18.8, "robot at rest")
    fsm.go(State.DONE, 45.0, 18.8, "teardown finished")
    assert fsm.execution_status == "completed" and fsm.interrupted_by is None


def test_cancel_reason_is_recorded_for_timeouts_and_interrupts():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm.timeout("nav_sim_timeout", 300.0, 132.5)
    assert fsm.cancel_reason == "nav_sim_timeout"
    fsm2 = RunStateMachine(LIM, 0.0, None)
    fsm2.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm2.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm2.go(State.EXECUTING, 31.0, 12.4, "goal accepted")
    fsm2.interrupt("SIGINT", 40.0, 15.0)
    assert fsm2.cancel_reason == "interrupt"


def test_odom_buffer_drops_the_old_timeline_after_a_reset():
    from robosim_eval.runner_fsm import append_sample
    buf = []
    for t in (44.0, 45.0, 46.48):          # before the sim_control reset
        append_sample(buf, (t, 0.0, 0.0), 400)
    for t in (0.05, 0.1, 12.6):            # after the reset the clock restarts near 0
        append_sample(buf, (t, 0.0, 0.0), 400)
    assert [s[0] for s in buf] == [0.05, 0.1, 12.6]


def test_odom_buffer_is_bounded():
    from robosim_eval.runner_fsm import append_sample
    buf = []
    for i in range(10):
        append_sample(buf, (float(i), 0.0, 0.0), 4)
    assert [s[0] for s in buf] == [6.0, 7.0, 8.0, 9.0]


class FakeClockFeed:
    """Stands in for rclpy.spin_once on a node whose /clock queue still holds messages from before a blocking call."""

    def __init__(self, stale, fresh):
        self.queue = list(stale)   # delivered one per spin, oldest first
        self.fresh = list(fresh)   # arrive only once the queue is empty and the spin is allowed to wait
        self.count, self.latest = 0, None

    def spin_once(self, timeout):
        if self.queue:
            self.latest = self.queue.pop(0)
            self.count += 1
        elif timeout > 0 and self.fresh:
            self.latest = self.fresh.pop(0)
            self.count += 1


def test_refresh_clock_drains_stale_messages_then_waits_for_a_fresh_one():
    feed = FakeClockFeed(stale=[1.0, 1.1, 1.2, 1.3, 1.4], fresh=[2.7, 2.8])
    assert refresh_clock(feed.spin_once, lambda: feed.count, wait_s=2.0) is True
    assert feed.latest == 2.7   # not 1.4, the last message queued during the blocking call


def test_refresh_clock_reports_when_no_fresh_message_arrives():
    feed = FakeClockFeed(stale=[1.0], fresh=[])
    t = [0.0]

    def now():
        t[0] += 0.1
        return t[0]

    assert refresh_clock(feed.spin_once, lambda: feed.count, wait_s=1.0, now=now) is False


# ---- review round 2 (runner-1, runner-6, runner-7, critic-2) --------------------------------------------------------

def test_the_accept_deadline_restarts_when_the_goal_is_sent():
    # runner-7: SEND_GOAL is entered before the recorder start; A5's 10 s acceptance wait counts from the goal itself
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    fsm.go(State.SEND_GOAL, 30.0, 12.0, "nav2 ready")
    fsm.restart("goal sent", 38.0, 14.0)
    assert fsm.state is State.SEND_GOAL and fsm.check(45.0, 15.0) is None      # 15 s after entry, 7 s after sending
    assert fsm.check(48.5, 15.5) == "accept_timeout"
    assert [h.reason for h in fsm.history][-2:] == ["nav2 ready", "goal sent"]


def test_the_stop_deadline_can_restart_after_an_injected_pause():
    # runner-6: the stop wait starts once the simulation plays again
    fsm = RunStateMachine(LIM, 0.0, None)
    for st, t in ((State.WAIT_READY, 1.0), (State.SEND_GOAL, 2.0), (State.EXECUTING, 3.0), (State.STOP_CONFIRM, 10.0)):
        fsm.go(st, t, None, "step")
    fsm.restart("simulation resumed", 16.0, None)
    assert fsm.check(25.0, None) is None and fsm.check(26.5, None) == "stop_timeout"


def test_restart_is_refused_in_other_states():
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.go(State.WAIT_READY, 1.0, None, "prepared")
    with pytest.raises(ValueError, match="WAIT_READY"):
        fsm.restart("no", 2.0, None)


def test_a_failure_can_abort_the_batch_even_during_teardown():
    # critic-2: Nav2 or the recorders not confirmed stopped at teardown: error and no further batch runs
    fsm = RunStateMachine(LIM, 0.0, None)
    fsm.fail("start_nav2.sh exit 4", 1.0, None)
    assert fsm.state is State.TEARDOWN and not fsm.abort_batch
    fsm.fail("stop_nav2.sh exit 1: Nav2 was not confirmed stopped", 2.0, None, abort=True)
    assert fsm.state is State.TEARDOWN and fsm.abort_batch and fsm.execution_status == "error"
    assert len(fsm.errors) == 2 and [h.state for h in fsm.history] == [State.PREPARE, State.TEARDOWN]
