"""D3 evaluator (plan doc A5): arrival, timeout, collision, cancel and unreachable judged separately.

Pure logic without ROS; inputs come from the runner (state machine facts, Nav2 terminal status), sim_control ground
truth, the Kit-side contact monitor and the offline data-integrity check. Tested with fixed inputs, including the four
mandatory bad-data cases (false success, missing contact data, time going backwards, cancel without acknowledgement).

Rules
- task_outcome: timeout (the runner canceled for a navigation deadline) > canceled (operator or injected cancel and a
  CANCELED terminal status) > reached (SUCCEEDED, stop confirmed, ground truth within tolerance) > unreachable (ABORTED
  or rejected, the scenario is preset unreachable with offline evidence, and ground truth did not reach the goal) >
  unknown (everything else; Nav2's raw status and error_code are kept, an abort is never read as unreachable by itself).
- safety_status: unknown without contact data (never "no collision"); fail on any contact between a robot body and
  something that is neither the robot nor an ignored prefix (the ground planes); otherwise pass.
- data_status: incomplete when a required stream (the judgement's inputs) is missing, has a wall gap above the dropout
  threshold or backward stamps, or /clock jumped backwards; informational streams (AMCL estimate) only add warnings.
- validation_status: fail on any failure evidence (execution error, cancel without acknowledgement, false success, not
  at rest, collision, an outcome different from the scenario's expectation); otherwise pass only when the outcome
  matches the expectation, safety passed, data is complete and the run completed; otherwise inconclusive.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

__all__ = ["ContactPolicy", "EvalInputs", "Verdict", "evaluate_run", "disallowed_contacts", "integrity_gap"]

STATUS_NAMES = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}


@dataclass(frozen=True)
class ContactPolicy:
    robot_root: str
    ignore_prefixes: Tuple[str, ...]


@dataclass(frozen=True)
class EvalInputs:
    scenario_expect: str                      # reached | unreachable | canceled | timeout
    preset_unreachable: bool                  # scenario labelled unreachable with offline evidence
    tolerance_m: float
    goal: Tuple[float, float]
    execution_status: str                     # from the runner state machine
    runner_errors: Tuple[str, ...]
    accepted: bool
    rejected: bool
    terminal_status: Optional[int]            # 4 SUCCEEDED, 5 CANCELED, 6 ABORTED, None = not seen
    error_code: Optional[int]
    cancel_requested: bool
    cancel_reason: Optional[str]              # interrupt | injected | nav_sim_timeout | nav_wall_timeout
    timeout_reason: Optional[str]
    stop_confirmed: bool
    gt_at_stop: Optional[Tuple[float, float]]  # ground-truth x, y when the robot came to rest (or at the end)
    contacts_measured: bool
    contacts: Sequence[Tuple[str, str]]       # (actor0, actor1) of every contact that started during the run
    required_gaps: Mapping[str, Optional[float]]    # max wall gap per required stream; None = no data
    required_backward: Mapping[str, int]
    informational_gaps: Mapping[str, Optional[float]]
    dropout_threshold_wall_s: float
    clock_backward_jumps: int


@dataclass(frozen=True)
class Verdict:
    execution_status: str
    task_outcome: str
    safety_status: str
    data_status: str
    validation_status: str
    fail_reasons: Tuple[str, ...]
    inconclusive_reasons: Tuple[str, ...]
    warnings: Tuple[str, ...]
    arrival_error_m: Optional[float]
    disallowed_contacts: Tuple[Tuple[str, str], ...]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def integrity_gap(entry: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Largest wall gap of one stream from the analyzer's data_integrity entry; None ("no data") unless the stream has
    messages inside the accept..arrival window (a whole-recording count is not evidence for the window)."""
    if not entry or not entry.get("count_in_window"):
        return None
    return entry.get("max_wall_gap_s")


def disallowed_contacts(contacts: Sequence[Tuple[str, str]], policy: ContactPolicy) -> Tuple[Tuple[str, str], ...]:
    out = []
    for a, b in contacts:
        ra, rb = _under(a, policy.robot_root), _under(b, policy.robot_root)
        if ra == rb:  # robot self contact, or not involving the robot
            continue
        other = b if ra else a
        if not any(other.startswith(p) for p in policy.ignore_prefixes):
            out.append((a, b))
    return tuple(out)


def evaluate_run(x: EvalInputs, policy: ContactPolicy) -> Verdict:
    fail: List[str] = []
    inconclusive: List[str] = []
    warnings: List[str] = []
    execution = x.execution_status
    if x.runner_errors:
        fail.append("runner errors: " + ", ".join(x.runner_errors))
    if x.cancel_requested and x.terminal_status is None:
        execution = "error"
        fail.append("cancel requested but no terminal status was acknowledged")

    err = math.hypot(x.gt_at_stop[0] - x.goal[0], x.gt_at_stop[1] - x.goal[1]) if x.gt_at_stop else None
    status = STATUS_NAMES.get(x.terminal_status, "none" if x.terminal_status is None else str(x.terminal_status))

    # data completeness first: unreachable needs complete logs
    data_problems = []
    for name, gap in x.required_gaps.items():
        if gap is None:
            data_problems.append(f"{name}: no data")
        elif gap > x.dropout_threshold_wall_s:
            data_problems.append(f"{name}: wall gap {gap:.3f} s > {x.dropout_threshold_wall_s} s")
    data_problems += [f"{n}: {c} backward stamps" for n, c in x.required_backward.items() if c]
    if x.clock_backward_jumps:
        data_problems.append(f"/clock jumped backwards {x.clock_backward_jumps} time(s) during the run")
    data_complete = not data_problems
    if not data_complete:
        inconclusive.append("data incomplete: " + "; ".join(data_problems))
    for name, gap in x.informational_gaps.items():
        if gap is None or gap > x.dropout_threshold_wall_s:
            warnings.append(f"informational stream {name}: " + ("no data" if gap is None else f"wall gap {gap:.3f} s"))

    if x.timeout_reason:
        outcome = "timeout"
    elif x.cancel_requested and x.terminal_status == 5 and x.cancel_reason in ("interrupt", "injected"):
        outcome = "canceled"
    elif x.terminal_status == 4:
        outcome = "unknown"
        if not x.stop_confirmed:
            fail.append("Nav2 SUCCEEDED but the robot was not confirmed at rest")
        elif err is None:
            inconclusive.append("no ground truth at the stop: arrival cannot be judged independently")
        elif err > x.tolerance_m:
            fail.append(f"false success: Nav2 SUCCEEDED but ground truth is {err:.3f} m from the goal "
                        f"(> {x.tolerance_m} m)")
        else:
            outcome = "reached"
    elif x.terminal_status == 6 or x.rejected:
        reached = err is not None and err <= x.tolerance_m
        if x.preset_unreachable and not reached and data_complete:
            outcome = "unreachable"
        else:
            outcome = "unknown"
            if x.scenario_expect == "reached":
                fail.append(f"Nav2 {('REJECTED' if x.rejected else status)} (error_code {x.error_code}) where the "
                            f"scenario expects the goal to be reached; cause not established, kept as unknown")
    else:
        outcome = "unknown"

    bad = disallowed_contacts(x.contacts, policy)
    if not x.contacts_measured:
        safety = "unknown"
        inconclusive.append("contact data missing: safety cannot be judged (not measured is not 'no collision')")
    elif bad:
        safety = "fail"
        fail.append(f"{len(bad)} contact(s) with non-ground objects, first {bad[0][0]} <-> {bad[0][1]}")
    else:
        safety = "pass"

    if outcome not in ("unknown", x.scenario_expect) and execution != "interrupted":
        # an operator interrupt is not evidence against the system: it ends inconclusive below, not failed
        fail.append(f"outcome {outcome} differs from the scenario expectation {x.scenario_expect}")
    if execution == "error" and not x.runner_errors and not any("acknowledged" in r for r in fail):
        fail.append("execution error")
    if execution == "interrupted":
        inconclusive.append("run interrupted by the operator")

    if fail:
        validation = "fail"
    elif outcome == x.scenario_expect and safety == "pass" and data_complete and execution == "completed":
        validation = "pass"
    else:
        validation = "inconclusive"
        if outcome == "unknown" and not inconclusive:
            inconclusive.append(f"task outcome unknown (terminal status {status})")
    return Verdict(execution_status=execution, task_outcome=outcome, safety_status=safety,
                   data_status="complete" if data_complete else "incomplete", validation_status=validation,
                   fail_reasons=tuple(fail), inconclusive_reasons=tuple(inconclusive), warnings=tuple(warnings),
                   arrival_error_m=err, disallowed_contacts=bad)
