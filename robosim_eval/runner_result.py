"""result.json of a D2/D3 run (plan doc A5/A6; contract C8): the D3 verdict inputs taken from the runner's facts, the
recording coverage checks and the final record. Pure functions of the runner's state, testable without ROS.

result.json top level: schema, execution_status, task_outcome, safety_status, data_status, validation_status,
verdict_reasons, evaluator, evaluator_inputs, runner, timing, nav2_raw, data_integrity, goal, target_goal, analyzer.
"analyzer" holds the offline analyzer's own output (its D0 verdict, arrival_check, positions, stop_still, coverage,
notes ...) or null when it did not run or failed; then goal, target_goal and nav2_raw come from the runner itself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from robosim_eval.config import BaselineConfig, Scenario
from robosim_eval.evaluator import EvalInputs, Verdict, integrity_gap, recording_coverage_problems
from robosim_eval.run_io import to_plain
from robosim_eval.runner_fsm import RunStateMachine

STOP_RECORD_DATA_CODES = {4: "a recorder exit code is missing", 5: "the bag is missing, unreadable or not copied",
                          6: "a required topic recorded 0 messages"}
ANALYZER_TOP_KEYS = ("timing", "nav2_raw", "data_integrity", "goal", "target_goal")
SCHEMA = ("robosim-eval run result (D3 runner verdict; the offline analyzer's own output is under 'analyzer', null "
          "when it did not run or failed)")


def read_analysis(run_dir: Path, analyze_exit: Optional[int]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """(the analyzer's result.json, None) when it ran and wrote one (exit 0/10/11); else (None, reason or None)."""
    path = run_dir / "result.json"
    if analyze_exit not in (0, 10, 11):
        return None, None
    if not path.exists():
        return None, f"the analyzer exited {analyze_exit} but wrote no result.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, f"the analyzer's result.json is unreadable: {type(exc).__name__}: {exc}"


def coverage_problems(run_dir: Path, facts: Dict[str, Any], opts: Any, cfg: BaselineConfig,
                      analysis: Optional[Dict[str, Any]]) -> List[str]:
    """Why the recording may not cover the run (A5: missing key data stays incomplete)."""
    codes, run = facts["exit_codes"], cfg.run
    if getattr(opts, "no_record", False):
        return ["no recording: the recorders were not started (--no-record)"]
    out = []
    if codes.get("stop_record") in STOP_RECORD_DATA_CODES:
        out.append(f"stop_record.sh exit {codes['stop_record']}: {STOP_RECORD_DATA_CODES[codes['stop_record']]}")
    try:
        bag_exit: Optional[str] = (run_dir / "bag.exit").read_text(encoding="utf-8").strip()
    except OSError:
        bag_exit = None
    if bag_exit == "124":
        out.append("the bag recorder hit its time cap (exit 124): the recording may end before the run")
    elif bag_exit not in (None, "0", "2"):  # 0, or 2 (SIGINT), when stop_record.sh stopped it
        out.append(f"the bag recorder ended with exit {bag_exit}")
    if analysis is None:
        if facts.get("analysis_error"):
            out.append(facts["analysis_error"])
        elif getattr(opts, "no_analyze", False):
            out.append("no offline analysis (--no-analyze): the recording was not checked")
        elif "analyze" not in codes:
            out.append("no recording to analyse (rosbag/ missing)")
        else:
            out.append(f"offline analysis failed (analyze_attempt.sh exit {codes['analyze']}; see analyze.txt)")
        return out
    end = facts.get("stop_confirmed_sim", facts.get("terminal_sim"))
    return out + recording_coverage_problems(analysis.get("coverage"), facts.get("accept_sim"), end,
                                             bool(facts.get("goal_id")), "terminal" in facts, run.required_streams,
                                             run.stop_max_gap_sim_s)


def eval_inputs(cfg: BaselineConfig, scenario: Scenario, facts: Dict[str, Any], fsm: RunStateMachine,
                clock_backward: int, coverage: List[str], analysis: Optional[Dict[str, Any]]) -> EvalInputs:
    """The evaluator's inputs from the runner facts, ground truth, contacts, the map check and the offline analysis.
    Without an analysis there is nothing per stream to judge: the coverage problems say why the data is incomplete."""
    run, f = cfg.run, facts
    integ = ((analysis or {}).get("data_integrity") or {}) if analysis is not None else None

    def gaps(names) -> Dict[str, Optional[float]]:
        return {n: integrity_gap(integ.get(n)) for n in names} if integ is not None else {}

    gt = f["ground_truth"].get("at_stop") or f["ground_truth"].get("at_end")
    term, g, contacts = f.get("terminal") or {}, scenario.goal, f["contacts"]
    return EvalInputs(
        scenario_expect=scenario.expect_outcome, preset_unreachable=scenario.preset_unreachable,
        tolerance_m=run.position_tolerance_m, goal=(g.x, g.y), execution_status=fsm.execution_status,
        runner_errors=tuple(fsm.errors), accepted=bool(f.get("goal_id")), rejected=bool(f.get("rejected")),
        terminal_status=term.get("status"), error_code=term.get("error_code"),
        cancel_requested=fsm.cancel_reason is not None, cancel_reason=fsm.cancel_reason,
        timeout_reason=fsm.timeout_reason, stop_confirmed="stop_confirmed_sim" in f,
        gt_at_stop=(gt["x"], gt["y"]) if gt else None, contacts_measured=bool(contacts.get("measured")),
        contacts=tuple(tuple(p) for p in contacts.get("found_pairs", [])),
        required_gaps=gaps(run.required_streams),
        required_backward={n: int((integ.get(n) or {}).get("backward_stamps", 0) or 0)
                           for n in run.required_streams} if integ is not None else {},
        informational_gaps=gaps(run.informational_streams),
        dropout_threshold_wall_s=run.dropout_wall_s, clock_backward_jumps=clock_backward,
        coverage_problems=tuple(coverage),
        contacts_dropped=int(contacts.get("dropped", 0) or 0) if contacts.get("measured") else 0,
        unreachable_evidence=(f.get("map_check") or {}).get("unreachable_evidence"),
        scenario_expect_safety=getattr(scenario, "expect_safety", None),
        scenario_expect_data=getattr(scenario, "expect_data", None))


def build_result(run_id: str, cfg: BaselineConfig, scenario: Scenario, facts: Dict[str, Any], fsm: RunStateMachine,
                 verdict: Verdict, inputs: EvalInputs, analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    g, term = scenario.goal, facts.get("terminal") or {}
    result: Dict[str, Any] = {
        "schema": SCHEMA, "execution_status": verdict.execution_status, "task_outcome": verdict.task_outcome,
        "safety_status": verdict.safety_status, "data_status": verdict.data_status,
        "validation_status": verdict.validation_status,
        "verdict_reasons": {"fail": list(verdict.fail_reasons), "inconclusive": list(verdict.inconclusive_reasons),
                            "warnings": list(verdict.warnings)},
        "evaluator": verdict.to_dict(), "evaluator_inputs": to_plain(inputs)}
    if analysis is not None:
        result.update({k: analysis.get(k) for k in ANALYZER_TOP_KEYS})
        result["analyzer"] = {k: v for k, v in analysis.items() if k not in ANALYZER_TOP_KEYS}
    else:
        result.update(goal={"frame": cfg.run.frame, "x": g.x, "y": g.y, "yaw": g.yaw,
                            "position_tolerance_m": cfg.run.position_tolerance_m,
                            "source": "scenario goal sent by the runner (no offline analysis)"},
                      target_goal={"id": facts.get("goal_id"), "id_source": "runner action client"},
                      timing=None, data_integrity=None, analyzer=None,
                      nav2_raw={"terminal_status_code": term.get("status"),
                                "terminal_status_name": term.get("name", "none"), "rejected": bool(facts.get("rejected")),
                                "error_code": term.get("error_code"), "error_msg": term.get("error_msg"),
                                "source": "runner action client (no offline analysis)"})
    result["runner"] = {"run_id": run_id, "scenario": scenario.name, "states": fsm.events(), "errors": fsm.errors,
                        "interrupted_by": fsm.interrupted_by, "timeout_reason": fsm.timeout_reason,
                        "abort_batch": fsm.abort_batch, **facts}
    return result
