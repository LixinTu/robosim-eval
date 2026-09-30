"""D3 evaluator (plan doc A5): arrival, timeout, collision, cancel and unreachable judged separately.

Pure logic without ROS; inputs come from the runner (state machine facts, Nav2 terminal status), sim_control ground
truth, the Kit-side contact monitor, the map check (robosim_eval.map_check) and the offline data-integrity check.
Tested with fixed inputs, including the four mandatory bad-data cases (false success, missing contact data, time going
backwards, cancel without acknowledgement).

Rules
- task_outcome: timeout (the runner canceled for a navigation deadline) > canceled (operator or injected cancel and a
  CANCELED terminal status) > reached (SUCCEEDED, stop confirmed, ground truth within tolerance) > unreachable (ABORTED
  with a planner no-path error code, the scenario is preset unreachable, the runner's map check found no path to the
  goal, ground truth did not reach the goal and the data is complete) > unknown (everything else: a rejection, any
  other abort code, missing ground truth; Nav2's raw status and error_code are kept, an abort is never read as
  unreachable by itself).
- safety_status: unknown without contact data or when the monitor lost contact events (never "no collision"); fail on
  any contact between a robot body and something that is neither the robot nor an ignored prefix (the ground planes),
  lost events or not; otherwise pass.
- data_status: incomplete when a required stream (the judgement's inputs) is missing, has a wall gap above the dropout
  threshold or backward stamps, /clock jumped backwards, or the recording does not cover the run (coverage problems
  from the runner: truncated bag, goal status not recorded, failed offline analysis); informational streams (AMCL
  estimate) only add warnings. Non-finite numbers never pass a comparison.
- validation_status: fail on any failure evidence (execution error, cancel without acknowledgement, false success, not
  at rest after a terminal status, collision, an outcome different from the scenario's expectation); otherwise pass
  only when the outcome matches the expectation, safety and data match theirs (default pass and complete; a fault
  injection scenario may expect safety fail or data incomplete) and the run completed; otherwise inconclusive.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

__all__ = ["ContactPolicy", "EvalInputs", "Verdict", "evaluate_run", "disallowed_contacts", "integrity_gap",
           "recording_coverage_problems", "NO_PATH_ERROR_CODES"]

STATUS_NAMES = {4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
# Error codes that name a missing path: nav2_msgs/action/ComputePathToPose.action (Jazzy) 207 TIMEOUT, 208 NO_VALID_PATH.
# The other planner codes (201 INVALID_PLANNER, 202 TF_ERROR, 203/204 START/GOAL_OUTSIDE_MAP, 205/206 START/GOAL_OCCUPIED)
# and the controller codes (FollowPath 1xx) name another cause, so they never support 'unreachable'.
NO_PATH_ERROR_CODES = (207, 208)
NO_GROUND_TRUTH = "no ground truth at the stop"


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
    coverage_problems: Tuple[str, ...] = ()   # the recording does not cover the run (makes the data incomplete)
    contacts_dropped: int = 0                 # contact events lost by the monitor; > 0 means safety cannot pass
    unreachable_evidence: Optional[bool] = None   # True only when the runner's map check found no path to the goal
    scenario_expect_safety: Optional[str] = None  # pass | fail (fault injection); None = pass
    scenario_expect_data: Optional[str] = None    # complete | incomplete (fault injection); None = complete


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


def _finite(*values: Any) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def integrity_gap(entry: Optional[Mapping[str, Any]]) -> Optional[float]:
    """Largest wall gap of one stream from the analyzer's data_integrity entry; None ("no data") unless the stream has
    messages inside the accept..arrival window (a whole-recording count is not evidence for the window)."""
    if not entry or not entry.get("count_in_window"):
        return None
    return entry.get("max_wall_gap_s")


def recording_coverage_problems(coverage: Optional[Mapping[str, Any]], start_sim: Optional[float],
                                end_sim: Optional[float], accepted: bool, terminal_seen: bool,
                                streams: Sequence[str], slack_sim_s: float) -> List[str]:
    """Does the recording cover the run as the runner saw it? `coverage` is the analyzer's coverage block (what the
    bag holds); start_sim..end_sim is the runner's goal acceptance .. stop confirmation (or terminal status) in
    simulation time. The analyzer's own window is taken from the bag, so a bag that ends early has no gap of its own:
    this comparison with the runner's facts is what catches it. A stream covers the run when its first sample is no
    later than start + slack and its last no earlier than end - slack (slack = one normal sample gap)."""
    if not coverage:
        return ["the offline analysis reported no recording coverage"]
    out = []
    if accepted and not coverage.get("target_goal_observed"):
        out.append("the target goal was not observed in the recording")
    elif accepted and not coverage.get("accepted_recorded"):
        out.append("the target goal's ACCEPTED/EXECUTING status was not recorded")
    if terminal_seen and not coverage.get("terminal_recorded"):
        out.append("the goal's terminal status was not recorded")
    spans = coverage.get("streams") or {}
    for name in streams:
        first, last = (spans.get(name) or {}).get("first_sim_s"), (spans.get(name) or {}).get("last_sim_s")
        if first is None or last is None or not _finite(first, last):
            out.append(f"{name}: no samples with a usable stamp in the recording")
            continue
        if start_sim is not None and first > start_sim + slack_sim_s:
            out.append(f"{name}: the recording starts at sim {first:.2f} s, after the goal was accepted "
                       f"({start_sim:.2f} s)")
        if end_sim is not None and last < end_sim - slack_sim_s:
            out.append(f"{name}: the recording ends at sim {last:.2f} s, before the run ended ({end_sim:.2f} s)")
    return out


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


def _arrival(x: EvalInputs) -> Tuple[Optional[float], Optional[str]]:
    """(distance from ground truth to the goal, None) when it can be judged, else (value or None, the reason)."""
    if not x.gt_at_stop:
        return None, NO_GROUND_TRUTH
    err = math.hypot(x.gt_at_stop[0] - x.goal[0], x.gt_at_stop[1] - x.goal[1])
    if not math.isfinite(err):
        return None, f"ground truth {tuple(x.gt_at_stop)} or goal {tuple(x.goal)} is not finite"
    if not _finite(x.tolerance_m) or x.tolerance_m <= 0:
        return err, f"position tolerance {x.tolerance_m!r} is not a positive finite number"
    return err, None


def _data_problems(x: EvalInputs) -> Tuple[List[str], List[str]]:
    """(measured dropouts: a required stream's wall gap above the threshold, every other data problem)."""
    gaps: List[str] = []
    other: List[str] = list(x.coverage_problems)
    thr = x.dropout_threshold_wall_s
    thr_ok = _finite(thr) and thr > 0
    if not thr_ok:
        other.append(f"dropout threshold {thr!r} is not a positive finite number")
    if not x.required_gaps and not x.coverage_problems:
        other.append("no required stream was checked")
    for name, gap in x.required_gaps.items():
        if gap is None:
            other.append(f"{name}: no data")
        elif not _finite(gap):
            other.append(f"{name}: wall gap {gap!r} is not a finite number")
        elif thr_ok and gap > thr:
            gaps.append(f"{name}: wall gap {gap:.3f} s > {thr} s")
    other += [f"{n}: {c} backward stamps" for n, c in x.required_backward.items() if c]
    if x.clock_backward_jumps:
        other.append(f"/clock jumped backwards {x.clock_backward_jumps} time(s) during the run")
    return gaps, other


def _unreachable_missing(x: EvalInputs, err: Optional[float], arrival_problem: Optional[str], data_complete: bool,
                         fail: List[str]) -> List[str]:
    """What is missing before an ABORTED or rejected goal of a preset-unreachable scenario counts as unreachable."""
    missing = []
    if x.rejected:
        missing.append(f"the goal was rejected, which names no cause (only ABORTED with a planner no-path error_code "
                       f"{list(NO_PATH_ERROR_CODES)} counts)")
    elif x.error_code not in NO_PATH_ERROR_CODES:
        missing.append(f"error_code {x.error_code} is not a planner no-path code {list(NO_PATH_ERROR_CODES)}")
    if x.unreachable_evidence is not True:
        missing.append("no map evidence that the goal is unreachable" +
                       (" (the map check found a path)" if x.unreachable_evidence is False else ""))
    if arrival_problem:
        missing.append(f"{arrival_problem}: not reaching the goal is not verified")
    elif err <= x.tolerance_m:
        missing.append(f"ground truth is {err:.3f} m from the goal")
        fail.append(f"ground truth reached the goal ({err:.3f} m <= {x.tolerance_m} m) although the scenario presets "
                    f"it as unreachable")
    if not data_complete:
        missing.append("data incomplete")
    return missing


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

    err, arrival_problem = _arrival(x)
    if arrival_problem and arrival_problem != NO_GROUND_TRUTH:
        inconclusive.append(f"{arrival_problem}: arrival cannot be judged")
    status = STATUS_NAMES.get(x.terminal_status, "none" if x.terminal_status is None else str(x.terminal_status))

    # data completeness first: unreachable needs complete logs
    gap_problems, other_problems = _data_problems(x)
    data_complete = not gap_problems and not other_problems
    expect_data = x.scenario_expect_data or "complete"
    data_as_expected = data_complete if expect_data == "complete" else \
        (expect_data == "incomplete" and bool(gap_problems) and not other_problems)
    if expect_data == "incomplete" and data_as_expected:
        warnings.append("expected by the scenario: data incomplete: " + "; ".join(gap_problems))
    elif not data_complete:
        inconclusive.append("data incomplete: " + "; ".join(gap_problems + other_problems))
    thr = x.dropout_threshold_wall_s
    for name, gap in x.informational_gaps.items():
        if gap is None or not _finite(gap, thr) or gap > thr:
            warnings.append(f"informational stream {name}: " + ("no data" if gap is None else f"wall gap {gap!r} s"))

    if x.terminal_status is not None and not x.stop_confirmed:  # A5: a terminal status alone is not a stop
        fail.append("Nav2 SUCCEEDED but the robot was not confirmed at rest" if x.terminal_status == 4 else
                    f"robot not confirmed at rest after the terminal status {status}")

    if x.timeout_reason:
        outcome = "timeout"
    elif x.cancel_requested and x.terminal_status == 5 and x.cancel_reason in ("interrupt", "injected"):
        outcome = "canceled"
    elif x.terminal_status == 4:
        outcome = "unknown"
        if not x.stop_confirmed:
            pass  # failed above
        elif arrival_problem == NO_GROUND_TRUTH:
            inconclusive.append("no ground truth at the stop: arrival cannot be judged independently")
        elif arrival_problem:
            pass  # the reason is recorded above
        elif err > x.tolerance_m:
            fail.append(f"false success: Nav2 SUCCEEDED but ground truth is {err:.3f} m from the goal "
                        f"(> {x.tolerance_m} m)")
        else:
            outcome = "reached"
    elif x.terminal_status == 6 or x.rejected:
        outcome = "unknown"
        if x.preset_unreachable:
            missing = _unreachable_missing(x, err, arrival_problem, data_complete, fail)
            if missing:
                inconclusive.append("not verified as unreachable: " + "; ".join(missing))
            else:
                outcome = "unreachable"
        if outcome == "unknown" and x.scenario_expect == "reached":
            fail.append(f"Nav2 {('REJECTED' if x.rejected else status)} (error_code {x.error_code}) where the "
                        f"scenario expects the goal to be reached; cause not established, kept as unknown")
    else:
        outcome = "unknown"

    bad = disallowed_contacts(x.contacts, policy)
    expect_safety = x.scenario_expect_safety or "pass"
    if not x.contacts_measured:
        safety = "unknown"
        inconclusive.append("contact data missing: safety cannot be judged (not measured is not 'no collision')")
    elif bad:
        safety = "fail"
        msg = f"{len(bad)} contact(s) with non-ground objects, first {bad[0][0]} <-> {bad[0][1]}"
        if expect_safety == "fail":
            warnings.append(f"expected by the scenario: {msg}")
        else:
            fail.append(msg)
    elif x.contacts_dropped:
        safety = "unknown"
        inconclusive.append(f"{x.contacts_dropped} contact event(s) were lost by the monitor: safety cannot be judged "
                            f"(lost is not 'no collision')")
    else:
        safety = "pass"
    if expect_safety == "fail" and safety == "pass":
        fail.append("safety pass differs from the scenario expectation fail (the injected contact was not detected)")
    if expect_data == "incomplete" and data_complete:
        fail.append("data complete differs from the scenario expectation incomplete (the injected dropout was not "
                    "detected)")
    if expect_safety not in ("pass", "fail"):
        inconclusive.append(f"unknown safety expectation {expect_safety!r}")
    if expect_data not in ("complete", "incomplete"):
        inconclusive.append(f"unknown data expectation {expect_data!r}")

    if outcome not in ("unknown", x.scenario_expect) and execution != "interrupted":
        # an operator interrupt is not evidence against the system: it ends inconclusive below, not failed
        fail.append(f"outcome {outcome} differs from the scenario expectation {x.scenario_expect}")
    if execution == "error" and not x.runner_errors and not any("acknowledged" in r for r in fail):
        fail.append("execution error")
    if execution == "interrupted":
        inconclusive.append("run interrupted by the operator")

    if fail:
        validation = "fail"
    elif outcome == x.scenario_expect and safety == expect_safety and data_as_expected and execution == "completed":
        validation = "pass"
    else:
        validation = "inconclusive"
        if outcome == "unknown" and not inconclusive:
            inconclusive.append(f"task outcome unknown (terminal status {status})")
    return Verdict(execution_status=execution, task_outcome=outcome, safety_status=safety,
                   data_status="complete" if data_complete else "incomplete", validation_status=validation,
                   fail_reasons=tuple(fail), inconclusive_reasons=tuple(inconclusive), warnings=tuple(warnings),
                   arrival_error_m=err, disallowed_contacts=bad)
