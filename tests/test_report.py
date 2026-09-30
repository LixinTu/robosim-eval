"""Fixed-input tests for the D4 batch report (plan doc A6 reporting rules), built only from saved run records."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from robosim_eval.report import load_runs, render_html, summarize
from robosim_eval.report import main as report_main


def make_run(root: Path, run_id: str, scenario: str, validation: str, outcome: str, safety="pass", data="complete",
             accept_to_result_sim=15.0, arrival=0.26, reasons=(), reset_error=0.001, commit="abc123", recoveries=0,
             contacts=()):
    d = root / run_id
    d.mkdir(parents=True)
    timing = None if accept_to_result_sim is None else {"accept_to_result_sim_s": accept_to_result_sim,
                                                        "accept_to_result_wall_s": accept_to_result_sim * 3}
    result = {
        "execution_status": "completed", "task_outcome": outcome, "safety_status": safety, "data_status": data,
        "validation_status": validation, "verdict_reasons": {"fail": list(reasons), "inconclusive": [], "warnings": []},
        "timing": timing,
        "nav2_raw": {"terminal_status_name": "SUCCEEDED" if outcome == "reached" else "ABORTED", "error_code": 0,
                     "recoveries": recoveries},
        "evaluator": {"arrival_error_m": arrival, "disallowed_contacts": [list(c) for c in contacts]},
        "runner": {"scenario": scenario, "run_id": run_id, "nav2_ready_wall_s": 13.5,
                   "ground_truth": {"after_reset": {"x": -6.0 + reset_error, "y": -1.0, "yaw": 3.14159}}},
    }
    (d / "events.jsonl").write_text(json.dumps({"event": "reset_check", "ok": True, "position_error_m": reset_error,
                                                "yaw_error_rad": 0.0}) + "\n", encoding="utf-8")
    (d / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({"run_id": run_id, "git": {"commit": commit, "dirty_tracked_files": False},
                                                 "versions": {"isaac_sim": "6.1.0", "navigation2": "1.3.13"}}),
                                     encoding="utf-8")
    return d


def batch(tmp_path: Path) -> Path:
    for i in range(3):
        make_run(tmp_path, f"normal-{i}", "normal", "pass", "reached", accept_to_result_sim=14.0 + i)
    make_run(tmp_path, "bypass-0", "bypass", "pass", "reached", accept_to_result_sim=20.0)
    make_run(tmp_path, "bypass-1", "bypass", "fail", "unknown", reasons=("Nav2 ABORTED (error_code 208) ...",),
             accept_to_result_sim=40.0)
    make_run(tmp_path, "bypass-2", "bypass", "pass", "reached", accept_to_result_sim=22.0)
    for i in range(3):
        make_run(tmp_path, f"unreachable-{i}", "unreachable", "pass", "unreachable", arrival=4.05)
    return tmp_path


def test_every_attempt_is_counted_including_failures(tmp_path: Path):
    runs = load_runs(batch(tmp_path))
    assert len(runs) == 9
    s = summarize(runs)
    assert s["bypass"]["attempts"] == 3 and s["bypass"]["validation"] == {"pass": 2, "fail": 1}


def test_average_time_is_success_only_and_labelled(tmp_path: Path):
    s = summarize(load_runs(batch(tmp_path)))
    assert s["bypass"]["mean_accept_to_result_sim_s_success_only"] == 21.0   # the failed 40 s run is excluded
    assert s["bypass"]["mean_basis"] == "reached + validation pass: 2 of 3 runs (mean over 2 with a time)"


def test_unreachable_is_grouped_separately_without_a_merged_success_rate(tmp_path: Path):
    html = render_html(load_runs(batch(tmp_path)), title="t")
    assert "unreachable" in html and "overall success rate" not in html.lower()
    assert html.index("normal") < html.index("unreachable")


def test_failure_cases_are_listed_with_reasons(tmp_path: Path):
    html = render_html(load_runs(batch(tmp_path)), title="t")
    assert "bypass-1" in html and "error_code 208" in html


def test_reset_evidence_and_versions_are_in_the_report(tmp_path: Path):
    html = render_html(load_runs(batch(tmp_path)), title="t")
    assert "abc123" in html and "6.1.0" in html and "1.3.13" in html
    assert "reset" in html.lower()


def test_run_dirs_without_result_are_reported_not_dropped(tmp_path: Path):
    batch(tmp_path)
    (tmp_path / "normal-broken").mkdir()
    runs = load_runs(tmp_path)
    assert len(runs) == 10 and any(r.run_id == "normal-broken" and r.validation == "missing" for r in runs)


def test_counts_are_written_as_text_not_python_dicts(tmp_path: Path):
    html = render_html(load_runs(batch(tmp_path)), title="t")
    assert "pass 2, fail 1" in html and "{&#x27;" not in html and "{'" not in html


def test_every_commit_in_the_batch_is_listed_with_its_run_count(tmp_path: Path):
    batch(tmp_path)
    make_run(tmp_path, "normal-9", "normal", "pass", "reached", commit="def456")
    html = render_html(load_runs(tmp_path), title="t")
    assert "abc123" in html and "def456" in html and "9 runs" in html and "1 run)" in html


def test_nav2_recoveries_are_shown_per_run_and_counted_per_scenario(tmp_path: Path):
    batch(tmp_path)
    make_run(tmp_path, "normal-9", "normal", "pass", "reached", recoveries=5)
    runs = load_runs(tmp_path)
    assert summarize(runs)["normal"]["runs_with_nav2_recoveries"] == 1
    assert "recoveries" in render_html(runs, title="t")


def test_reset_error_comes_from_the_recorded_reset_check(tmp_path: Path):
    make_run(tmp_path, "normal-0", "normal", "pass", "reached", reset_error=0.00007)
    (run,) = load_runs(tmp_path)
    assert run.reset_error_m == 0.00007


def test_distance_column_is_labelled_as_final_distance_to_goal(tmp_path: Path):
    html = render_html(load_runs(batch(tmp_path)), title="t")
    assert "final distance to goal" in html


# ---- review round D4 (report_batch-4/-5/-7/-10, critic-3): what the numbers are based on ----------------------------

def test_mean_time_excludes_reached_runs_that_failed_validation(tmp_path: Path):
    make_run(tmp_path, "bypass-0", "bypass", "pass", "reached", accept_to_result_sim=20.0)
    make_run(tmp_path, "bypass-1", "bypass", "fail", "reached", safety="fail", accept_to_result_sim=60.0,
             reasons=("1 contact(s) with non-ground objects",), contacts=(("/World/Carter/wheel", "/World/Box"),))
    make_run(tmp_path, "bypass-2", "bypass", "inconclusive", "reached", data="incomplete", accept_to_result_sim=90.0)
    make_run(tmp_path, "bypass-3", "bypass", "pass", "reached", accept_to_result_sim=22.0)
    s = summarize(load_runs(tmp_path))
    assert s["bypass"]["mean_accept_to_result_sim_s_success_only"] == 21.0   # the fail and inconclusive runs are out
    assert s["bypass"]["mean_basis"] == "reached + validation pass: 2 of 4 runs (mean over 2 with a time)"


def test_mean_basis_counts_successful_runs_that_have_no_time(tmp_path: Path):
    make_run(tmp_path, "normal-0", "normal", "pass", "reached", accept_to_result_sim=15.0)
    make_run(tmp_path, "normal-1", "normal", "pass", "reached", accept_to_result_sim=18.0)
    make_run(tmp_path, "normal-2", "normal", "pass", "reached", accept_to_result_sim=None)
    s = summarize(load_runs(tmp_path))
    assert s["normal"]["mean_accept_to_result_sim_s_success_only"] == 16.5
    assert s["normal"]["mean_basis"] == "reached + validation pass: 3 of 3 runs (mean over 2 with a time)"


def scenario_row(html: str, name: str) -> Dict[str, str]:
    """The per-scenario table row of one scenario, keyed by the column headers."""
    table = html[html.index("<h2>Per scenario</h2>"):]
    table = table[:table.index("</table>")]
    heads = re.findall(r"<th>(.*?)</th>", table[:table.index("</tr>")], flags=re.S)
    row = table[table.index(f"<tr><th>{name}</th>"):]
    cells = [name] + re.findall(r"<td>(.*?)</td>", row[:row.index("</tr>")], flags=re.S)
    return dict(zip(heads, cells))


def test_collisions_are_not_counted_as_zero_when_contacts_were_not_measured(tmp_path: Path):
    for i in range(3):
        make_run(tmp_path, f"bypass-{i}", "bypass", "inconclusive", "reached", safety="unknown")
    (tmp_path / "bypass-broken").mkdir()   # no result.json: nothing measured either
    runs = load_runs(tmp_path)
    s = summarize(runs)
    assert s["bypass"]["collisions"] is None and s["bypass"]["collisions_measured_runs"] == 0
    cell = scenario_row(render_html(runs, title="t"), "bypass")["collisions"]
    assert cell.startswith("not measured") and not cell.startswith("0")


def test_collisions_count_only_measured_runs_and_say_how_many(tmp_path: Path):
    make_run(tmp_path, "collision-0", "collision", "fail", "reached", safety="fail",
             contacts=(("/World/Carter/wheel", "/World/Box"),))
    make_run(tmp_path, "collision-1", "collision", "pass", "reached", safety="pass")
    make_run(tmp_path, "collision-2", "collision", "inconclusive", "reached", safety="unknown")
    runs = load_runs(tmp_path)
    s = summarize(runs)
    assert s["collision"]["collisions"] == 1 and s["collision"]["collisions_measured_runs"] == 2
    assert "2 of 3 runs measured" in render_html(runs, title="t")


def _analyzer_only_result(d: Path) -> None:
    """What analyze_attempt.py leaves when the runner dies before it merges the D3 verdict (no runner/evaluator)."""
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({
        "schema": "robosim-eval attempt result, D0 (plan doc A5)", "execution_status": "completed",
        "task_outcome": "reached", "safety_status": "unknown", "data_status": "complete", "validation_status": "pass",
        "verdict_reasons": {"fail": [], "inconclusive": []},
        "timing": {"accept_to_result_sim_s": 8.5, "accept_to_result_wall_s": 25.6}}), encoding="utf-8")


def test_result_without_the_d3_evaluator_is_never_shown_as_pass(tmp_path: Path):
    _analyzer_only_result(tmp_path / "bypass-20260930-020000")
    runs = load_runs(tmp_path)
    (run,) = runs
    assert run.validation == "not D3-evaluated" and run.outcome == "unknown" and run.collisions is None
    s = summarize(runs)
    assert "pass" not in s["bypass"]["validation"] and s["bypass"]["mean_accept_to_result_sim_s_success_only"] is None
    html = render_html(runs, title="t")
    assert "<tr class='ok'>" not in html
    failures = html[html.index("Failure and inconclusive cases"):html.index("All attempts")]
    assert "bypass-20260930-020000" in failures and "offline analyzer" in failures


def test_trajectory_section_names_its_source_and_frame(tmp_path: Path):
    html = render_html(load_runs(batch(tmp_path)), title="t")
    section = html[html.index("<h2>Trajectories</h2>"):html.index("Failure and inconclusive cases")]
    assert "spawn pose plus ideal odometry" in section and "map frame" in section
    assert "not the sim_control ground truth" in section


# ---- review round D4 (report_batch-1/-2): the batch record (batch.json) and the fate of every planned attempt --------

def write_batch(batch_dir: Path, attempts: List[dict], status: Optional[int], stopped_by: Optional[str] = None,
                **extra) -> Path:
    batch_dir.mkdir(parents=True, exist_ok=True)
    scenarios = list(dict.fromkeys(a["scenario"] for a in attempts))
    rec = {"scenarios": scenarios, "repeats": max(a["repeat"] for a in attempts), "attempts": attempts,
           "stopped_by": stopped_by, "status": status, **extra}
    (batch_dir / "batch.json").write_text(json.dumps(rec), encoding="utf-8")
    return batch_dir / "batch.json"


def attempt(i: int, scenario: str, repeat: int, rc: Optional[int], run_dir: Optional[Path] = None,
            note: str = "") -> dict:
    a = {"index": i, "scenario": scenario, "repeat": repeat, "exit": rc}
    if run_dir is not None:
        a["run_dir"] = str(run_dir)
    if note:
        a["note"] = note
    return a


def read_report(runs: Path):
    return (runs / "report.html").read_text(encoding="utf-8"), json.loads((runs / "summary.json").read_text("utf-8"))


def test_aborted_batch_is_stated_and_every_not_run_attempt_is_listed(tmp_path: Path):
    runs = tmp_path / "runs"
    a0 = make_run(runs, "normal-20260930-100000", "normal", "pass", "reached")
    a1 = make_run(runs, "bypass-20260930-100400", "bypass", "fail", "unknown", reasons=("stop not confirmed",))
    plan = [("normal", 1), ("bypass", 1), ("unreachable", 1), ("normal", 2), ("bypass", 2), ("unreachable", 2)]
    atts = [attempt(0, "normal", 1, 0, a0), attempt(1, "bypass", 1, 31, a1)]
    atts += [attempt(i, sc, rep, None, note="not run: batch aborted") for i, (sc, rep) in enumerate(plan) if i >= 2]
    bj = write_batch(tmp_path, atts, 31, state="aborted",
                     abort_reason="attempt 1 (bypass, repeat 1): runner exit 31: a cancel or stop was not confirmed")
    assert report_main([str(runs), "--batch-json", str(bj)]) == 0
    html, summ = read_report(runs)
    assert "Batch aborted" in html and "runner exit 31" in html
    assert "2 of 6 planned attempts ran" in html and "4 not run" in html
    table = html[html.index("<h2>Batch attempts</h2>"):]
    assert table.count("not run (batch aborted)") == 4 and "aborted the batch" in table
    assert summ["batch"]["state"] == "aborted" and summ["batch"]["planned"] == 6 and summ["batch"]["not_run"] == 4
    assert [a["fate"] for a in summ["attempts"]][:2] == ["ran (runner exit 0)", "ran (runner exit 31); aborted the batch"]
    assert summ["scenarios"]["unreachable"]["attempts"] == 0 and summ["scenarios"]["unreachable"]["not_run"] == 2


def test_interrupted_batch_is_stated_in_the_headline(tmp_path: Path):
    runs = tmp_path / "runs"
    a0 = make_run(runs, "normal-20260930-100000", "normal", "inconclusive", "unknown")
    atts = [attempt(0, "normal", 1, 20, a0), attempt(1, "bypass", 1, None, note="not run: batch interrupted")]
    bj = write_batch(tmp_path, atts, 20, stopped_by="SIGINT")
    assert report_main([str(runs), "--batch-json", str(bj)]) == 0
    html, summ = read_report(runs)
    assert "Batch interrupted" in html and "SIGINT" in html and "not run (batch interrupted)" in html
    assert summ["batch"]["state"] == "interrupted" and summ["batch"]["stopped_by"] == "SIGINT"


def test_attempts_that_left_no_run_dir_are_counted_with_their_exit_code(tmp_path: Path):
    runs = tmp_path / "runs"
    a0 = make_run(runs, "normal-20260930-100000", "normal", "pass", "reached")
    atts = [attempt(0, "normal", 1, 0, a0), attempt(1, "bypas", 1, 2), attempt(2, "normal", 2, 2)]
    bj = write_batch(tmp_path, atts, 0)
    assert report_main([str(runs), "--batch-json", str(bj)]) == 0
    html, summ = read_report(runs)
    assert "Engineering trial of 3 attempts" in html
    assert summ["scenarios"]["normal"]["attempts"] == 2
    assert summ["scenarios"]["normal"]["validation"] == {"pass": 1, "missing": 1}
    assert summ["scenarios"]["bypas"]["attempts"] == 1
    assert [a["fate"] for a in summ["attempts"]][1:] == ["no run dir (runner exit 2)"] * 2
    assert html.count("no run dir (runner exit 2)") >= 2


def test_every_attempt_exit_2_still_writes_a_report(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    bj = write_batch(tmp_path, [attempt(i, "normal", i + 1, 2) for i in range(3)], 0)
    assert report_main([str(runs), "--batch-json", str(bj)]) == 0
    _html, summ = read_report(runs)
    assert summ["scenarios"]["normal"]["validation"] == {"missing": 3}


def test_report_without_runs_or_batch_record_is_an_error(tmp_path: Path):
    (tmp_path / "runs").mkdir()
    assert report_main([str(tmp_path / "runs")]) == 2
    assert not (tmp_path / "runs" / "report.html").exists()


def test_run_dirs_no_attempt_claims_are_flagged_and_not_counted(tmp_path: Path):
    runs = tmp_path / "runs"
    a0 = make_run(runs, "normal-20260930-100000", "normal", "pass", "reached")
    make_run(runs, "normal-20260930-120000", "normal", "fail", "unknown")   # e.g. a manual rerun into runs/
    bj = write_batch(tmp_path, [attempt(0, "normal", 1, 0, a0)], 0)
    assert report_main([str(runs), "--batch-json", str(bj)]) == 0
    html, summ = read_report(runs)
    assert summ["scenarios"]["normal"]["attempts"] == 1 and summ["unclaimed_run_dirs"] == ["normal-20260930-120000"]
    assert "not claimed by any attempt" in html


def test_legacy_batch_record_is_reconciled_through_the_attempt_logs(tmp_path: Path):
    """D4/D5 batch.json files carry no run_dir; each attempt's log starts with the runner's 'run dir:' line."""
    runs = tmp_path / "runs"
    dirs = [make_run(runs, "normal-20260930-013010", "normal", "pass", "reached"),
            make_run(runs, "bypass-20260930-013406", "bypass", "pass", "reached")]
    for i, (sc, d) in enumerate(zip(("normal", "bypass"), dirs)):
        (tmp_path / f"{i:02d}-{sc}-1.txt").write_text(f"run dir: /mnt/d/elsewhere/runs/{d.name}\n{{}}\n", "utf-8")
    write_batch(tmp_path, [attempt(0, "normal", 1, 0), attempt(1, "bypass", 1, 0)], 0)
    assert report_main([str(runs)]) == 0          # ../batch.json is found next to runs/
    html, summ = read_report(runs)
    assert summ["batch"]["state"] == "completed" and summ["unclaimed_run_dirs"] == []
    assert [a["run_id"] for a in summ["attempts"]] == [d.name for d in dirs]
    assert "Batch completed" in html and "2 of 2 planned attempts ran" in html


def test_batch_record_that_never_finished_says_so(tmp_path: Path):
    runs = tmp_path / "runs"
    a0 = make_run(runs, "normal-20260930-100000", "normal", "pass", "reached")
    atts = [attempt(0, "normal", 1, 0, a0), attempt(1, "bypass", 1, None, note="running"),
            attempt(2, "unreachable", 1, None, note="pending")]
    bj = write_batch(tmp_path, atts, None, state="running")
    assert report_main([str(runs), "--batch-json", str(bj)]) == 0
    html, summ = read_report(runs)
    assert "did not finish" in html and summ["batch"]["state"] == "running"
    assert [a["fate"] for a in summ["attempts"]][1:] == [
        "started; no exit recorded (the batch record ends during this attempt)",
        "not run (the batch record ends before it)"]
