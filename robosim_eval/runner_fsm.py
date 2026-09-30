"""D2 run state machine (plan doc A5): allowed transitions, per-state deadlines and the final execution status.

Pure logic without ROS, driven by robosim_eval.runner; tested with fixed inputs (tests/test_runner_fsm.py).

  PREPARE -> WAIT_READY -> SEND_GOAL -> EXECUTING -> STOP_CONFIRM -> TEARDOWN -> DONE
                                          EXECUTING -> CANCELING -> STOP_CONFIRM
  any state before TEARDOWN -> TEARDOWN (failure, rejection, interrupt before the goal, unconfirmed cancel or stop)

Deadlines (A5 candidates; wall = host monotonic seconds, sim = /clock seconds):
  WAIT_READY ready_wall_s, SEND_GOAL accept_wall_s, EXECUTING nav_sim_s of simulation time or nav_wall_s of wall time
  (whichever comes first), CANCELING cancel_wall_s, STOP_CONFIRM stop_wall_s.
Final status: "error" after any failure or an unconfirmed cancel/stop (the latter two also set abort_batch, because
the plan stops further batch runs when a stop is not confirmed); otherwise "interrupted" after an interrupt; otherwise
"completed". A navigation timeout is not an execution error: it is kept in timeout_reason for the task verdict.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, List, Optional


class State(enum.Enum):
    PREPARE = "PREPARE"
    WAIT_READY = "WAIT_READY"
    SEND_GOAL = "SEND_GOAL"
    EXECUTING = "EXECUTING"
    CANCELING = "CANCELING"
    STOP_CONFIRM = "STOP_CONFIRM"
    TEARDOWN = "TEARDOWN"
    DONE = "DONE"


_ALLOWED = {
    State.PREPARE: {State.WAIT_READY, State.TEARDOWN},
    State.WAIT_READY: {State.SEND_GOAL, State.TEARDOWN},
    State.SEND_GOAL: {State.EXECUTING, State.TEARDOWN},
    State.EXECUTING: {State.STOP_CONFIRM, State.CANCELING, State.TEARDOWN},
    State.CANCELING: {State.STOP_CONFIRM, State.TEARDOWN},
    State.STOP_CONFIRM: {State.TEARDOWN},
    State.TEARDOWN: {State.DONE},
    State.DONE: set(),
}
_ABORTING_TIMEOUTS = {"cancel_timeout", "stop_timeout"}
_ERROR_TIMEOUTS = {"ready_timeout", "accept_timeout"} | _ABORTING_TIMEOUTS


@dataclass(frozen=True)
class Limits:
    ready_wall_s: float
    accept_wall_s: float
    nav_sim_s: float
    nav_wall_s: float
    cancel_wall_s: float
    stop_wall_s: float


@dataclass(frozen=True)
class Transition:
    state: State
    t_wall: float
    t_sim: Optional[float]
    reason: str


def deadline_exceeded(state: State, entered_wall: float, entered_sim: Optional[float], t_wall: float,
                      t_sim: Optional[float], lim: Limits) -> Optional[str]:
    """Name of the deadline that has passed in `state`, or None."""
    waited = t_wall - entered_wall
    if state is State.WAIT_READY and waited > lim.ready_wall_s:
        return "ready_timeout"
    if state is State.SEND_GOAL and waited > lim.accept_wall_s:
        return "accept_timeout"
    if state is State.EXECUTING:
        if entered_sim is not None and t_sim is not None and t_sim - entered_sim > lim.nav_sim_s:
            return "nav_sim_timeout"
        if waited > lim.nav_wall_s:
            return "nav_wall_timeout"
    if state is State.CANCELING and waited > lim.cancel_wall_s:
        return "cancel_timeout"
    if state is State.STOP_CONFIRM and waited > lim.stop_wall_s:
        return "stop_timeout"
    return None


class RunStateMachine:
    def __init__(self, limits: Limits, t_wall: float, t_sim: Optional[float]) -> None:
        self.limits = limits
        self.history: List[Transition] = [Transition(State.PREPARE, t_wall, t_sim, "run started")]
        self.errors: List[str] = []
        self.interrupted_by: Optional[str] = None
        self.timeout_reason: Optional[str] = None
        self.abort_batch = False

    @property
    def state(self) -> State:
        return self.history[-1].state

    @property
    def entered(self) -> Transition:
        return self.history[-1]

    def go(self, new: State, t_wall: float, t_sim: Optional[float], reason: str) -> None:
        if new not in _ALLOWED[self.state]:
            raise ValueError(f"illegal transition {self.state.name} -> {new.name} ({reason})")
        self.history.append(Transition(new, t_wall, t_sim, reason))

    def check(self, t_wall: float, t_sim: Optional[float]) -> Optional[str]:
        e = self.entered
        return deadline_exceeded(self.state, e.t_wall, e.t_sim, t_wall, t_sim, self.limits)

    def timeout(self, name: str, t_wall: float, t_sim: Optional[float]) -> None:
        """Apply a passed deadline: navigation timeouts cancel the goal; the others end the run with an error."""
        if name in ("nav_sim_timeout", "nav_wall_timeout"):
            self.timeout_reason = name
            self.go(State.CANCELING, t_wall, t_sim, name)
            return
        if name not in _ERROR_TIMEOUTS:
            raise ValueError(f"unknown timeout {name}")
        self.errors.append(name)
        self.abort_batch = self.abort_batch or name in _ABORTING_TIMEOUTS
        self.go(State.TEARDOWN, t_wall, t_sim, name)

    def interrupt(self, why: str, t_wall: float, t_sim: Optional[float]) -> None:
        """Operator interrupt: cancel a running goal, otherwise go straight to teardown."""
        self.interrupted_by = self.interrupted_by or why
        if self.state is State.EXECUTING:
            self.go(State.CANCELING, t_wall, t_sim, f"interrupt ({why})")
        elif self.state not in (State.CANCELING, State.STOP_CONFIRM, State.TEARDOWN, State.DONE):
            self.go(State.TEARDOWN, t_wall, t_sim, f"interrupt ({why})")

    def fail(self, why: str, t_wall: float, t_sim: Optional[float]) -> None:
        self.errors.append(why)
        if self.state not in (State.TEARDOWN, State.DONE):
            self.go(State.TEARDOWN, t_wall, t_sim, f"failure: {why}")

    @property
    def execution_status(self) -> str:
        if self.errors:
            return "error"
        return "interrupted" if self.interrupted_by else "completed"

    def events(self) -> List[Dict[str, object]]:
        return [{"state": h.state.name, "t_wall": h.t_wall, "t_sim": h.t_sim, "reason": h.reason} for h in self.history]


class StopStillTracker:
    """Online stop-still check on sim-stamped odometry twist (the same rule as analyze_attempt.stop_still): |v| below
    `linear` and |w| below `angular` continuously for `hold_s` of simulation time. A gap between samples larger than
    `max_gap_s` or a backward stamp restarts the window. Once confirmed, the confirmation time is kept."""

    def __init__(self, linear: float, angular: float, hold_s: float, max_gap_s: float) -> None:
        self.linear, self.angular, self.hold_s, self.max_gap_s = linear, angular, hold_s, max_gap_s
        self._start: Optional[float] = None
        self._prev: Optional[float] = None
        self.confirmed_at: Optional[float] = None

    def update(self, t: float, v: float, w: float) -> Optional[float]:
        if self.confirmed_at is not None:
            return self.confirmed_at
        if self._prev is not None and (t - self._prev > self.max_gap_s + 1e-9 or t < self._prev):
            self._start = None
        self._prev = t
        if abs(v) < self.linear and abs(w) < self.angular:
            if self._start is None:
                self._start = t
            if t - self._start >= self.hold_s - 1e-9:
                self.confirmed_at = t
                return t
        else:
            self._start = None
        return None


def doctor_retry(exit_code: int, attempt: int, max_attempts: int) -> bool:
    """Retry the pre-run doctor only for 'degraded' (12): after a sim_control reset the lidar publisher is re-created
    and its first seconds are irregular (0-1 frames in a window was measured, artifacts/d2/repro-doctor-after-reset).
    Healthy, not advancing, missing data, environment errors and hangs are never retried; attempts are bounded."""
    return exit_code == 12 and attempt < max_attempts
