"""Fixed-input tests for the D4 batch report (plan doc A6 reporting rules), built only from saved run records."""
from __future__ import annotations

import json
from pathlib import Path

from robosim_eval.report import load_runs, render_html, summarize


def make_run(root: Path, run_id: str, scenario: str, validation: str, outcome: str, safety="pass", data="complete",
             accept_to_result_sim=15.0, arrival=0.26, reasons=(), reset_error=0.001, commit="abc123", recoveries=0):
    d = root / run_id
    d.mkdir(parents=True)
    result = {
        "execution_status": "completed", "task_outcome": outcome, "safety_status": safety, "data_status": data,
        "validation_status": validation, "verdict_reasons": {"fail": list(reasons), "inconclusive": [], "warnings": []},
        "timing": {"accept_to_result_sim_s": accept_to_result_sim, "accept_to_result_wall_s": accept_to_result_sim * 3},
        "nav2_raw": {"terminal_status_name": "SUCCEEDED" if outcome == "reached" else "ABORTED", "error_code": 0,
                     "recoveries": recoveries},
        "evaluator": {"arrival_error_m": arrival, "disallowed_contacts": []},
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
    assert s["bypass"]["mean_basis"] == "reached runs only (2 of 3)"


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
