"""D4 batch report: a static HTML page built only from saved run records (plan doc A3 report.py, A6 reporting rules).

  python3 -m robosim_eval.report <runs_dir> [--batch-json <batch.json>] [--title T]
      ->  <runs_dir>/report.html and <runs_dir>/summary.json (exit 0; 2 when there is neither a run nor a batch record)
The batch record defaults to <runs_dir>/../batch.json when it exists (robosim_eval.batch writes it there).
Rules applied (A5, A6): every planned attempt is listed with its fate (ran, no run dir, not run, the one that aborted
the batch) and the page headline says whether the batch completed, was aborted or interrupted; every attempt that
started is counted, failed and broken ones included; average times are over successful runs only (reached and
validation pass) and say how many runs that is; collisions are counted only over runs whose contacts were measured
(not measured is never shown as zero); a result.json without the D3 evaluator verdict is shown as "not D3-evaluated",
never as pass; each scenario is its own group, so unreachable goals are never merged into a success rate; failure
cases are listed with their reasons; versions, commit and the reset evidence are shown. The 9-run batch is an
engineering trial, not a navigation performance claim (A4), and the page says so.
"""
from __future__ import annotations

import argparse
import base64
import csv
import dataclasses
import html
import json
import statistics
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

VENDOR_MAP = Path.home() / "robotics/vendor/isaac-ros-6.1/jazzy_ws/src/navigation/carter_navigation/maps"
SCENARIO_ORDER = ["normal", "bypass", "unreachable"]
NOT_EVALUATED = "not D3-evaluated"
MEASURED_SAFETY = ("pass", "fail")   # the evaluator judges safety only from measured contact data
STATE_BY_STATUS = {0: "completed", 20: "interrupted", 31: "aborted"}   # batch.json files written before "state"


@dataclass
class RunRecord:
    run_id: str
    path: Path
    scenario: str
    validation: str
    outcome: str
    safety: str
    data: str
    execution: str
    reasons: List[str]
    warnings: List[str]
    arrival_error_m: Optional[float]
    accept_to_result_sim_s: Optional[float]
    accept_to_result_wall_s: Optional[float]
    nav2_status: Optional[str]
    nav2_error_code: Optional[int]
    reset_error_m: Optional[float]
    collisions: Optional[int]          # disallowed contacts; None = contacts not measured (never read as zero)
    manifest: Dict[str, Any] = field(default_factory=dict)
    recoveries: Optional[int] = None
    runner_exit: Optional[int] = None  # from the batch record, when there is one


@dataclass
class AttemptRow:
    """One planned attempt of a batch and what became of it."""
    index: int
    scenario: str
    repeat: int
    exit: Optional[int]
    wall_s: Optional[float]
    run_id: Optional[str]
    fate: str


@dataclass
class BatchView:
    """The batch record (batch.json) reconciled with the run directories found under runs/."""
    record: str
    state: str                  # completed | aborted | interrupted | running (the batch never closed out)
    status: Optional[int]
    stopped_by: Optional[str]
    abort_reason: Optional[str]
    attempts: List[AttemptRow]
    records: List[RunRecord]    # the runs counted: one per started attempt, placeholders included
    unclaimed: List[str]        # run dirs under runs/ that no attempt of this batch claims (not counted)

    @property
    def planned(self) -> int:
        return len(self.attempts)

    @property
    def ran(self) -> int:
        return sum(1 for a in self.attempts if a.exit is not None)

    @property
    def not_run(self) -> int:
        return sum(1 for a in self.attempts if a.fate.startswith("not run"))


def _load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _reset_error(run_dir: Path) -> Optional[float]:
    """Ground-truth distance to the spawn after the reset, as the runner recorded it (events.jsonl reset_check)."""
    try:
        with open(run_dir / "events.jsonl", encoding="utf-8") as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("event") == "reset_check":
                    return ev.get("position_error_m")
    except (OSError, ValueError):
        return None
    return None


def _placeholder(run_id: str, path: Path, scenario: str, reason: str, manifest: Optional[Dict[str, Any]] = None,
                 runner_exit: Optional[int] = None) -> RunRecord:
    """An attempt without a usable D3 verdict: counted, never passed, nothing measured."""
    return RunRecord(run_id, path, scenario, "missing", "unknown", "unknown", "incomplete", "error", [reason], [],
                     None, None, None, None, None, None, None, manifest or {}, None, runner_exit)


def load_run(d: Path) -> RunRecord:
    r, m = _load(d / "result.json"), _load(d / "manifest.json") or {}
    scenario = ((r or {}).get("runner") or {}).get("scenario") or d.name.rsplit("-", 2)[0].split("-")[0]
    if r is None:
        return _placeholder(d.name, d, scenario, "result.json missing or unreadable", m)
    vr = r.get("verdict_reasons") or {}
    tm, nav = r.get("timing") or {}, r.get("nav2_raw") or {}
    base = dict(run_id=d.name, path=d, scenario=scenario, accept_to_result_sim_s=tm.get("accept_to_result_sim_s"),
                accept_to_result_wall_s=tm.get("accept_to_result_wall_s"), nav2_status=nav.get("terminal_status_name"),
                nav2_error_code=nav.get("error_code"), reset_error_m=_reset_error(d), manifest=m,
                recoveries=nav.get("recoveries"))
    if "evaluator" not in r:
        # only _write_result adds the D3 verdict; without it the top-level statuses are the offline analyzer's (the
        # runner died before its close-out) or a pre-D3 runner's, and a pass there is not an A5 pass
        recorded = ", ".join(f"{k} {r.get(k + '_status', '-')}" for k in ("validation", "safety", "data"))
        why = ("pre-D3 runner record without an evaluator verdict" if "runner" in r else
               "only the offline analyzer verdict exists (the runner did not finish its close-out)")
        return RunRecord(**base, validation=NOT_EVALUATED, outcome="unknown", safety="unknown", data="incomplete",
                         execution=r.get("execution_status", "error") if "runner" in r else "error",
                         reasons=[f"{NOT_EVALUATED}: {why}; recorded {recorded}, outcome "
                                  f"{r.get('task_outcome', '-')} are not used"],
                         warnings=[], arrival_error_m=None, collisions=None)
    ev = r.get("evaluator") or {}
    safety = r.get("safety_status", "unknown")
    bad = ev.get("disallowed_contacts") or []
    return RunRecord(**base, validation=r.get("validation_status", "missing"), outcome=r.get("task_outcome", "unknown"),
                     safety=safety, data=r.get("data_status", "incomplete"), execution=r.get("execution_status", "error"),
                     reasons=list(vr.get("fail", [])) + list(vr.get("inconclusive", [])),
                     warnings=list(vr.get("warnings", [])), arrival_error_m=ev.get("arrival_error_m"),
                     collisions=len(bad) if safety in MEASURED_SAFETY or bad else None)


def load_runs(runs_dir: Path) -> List[RunRecord]:
    return [load_run(d) for d in sorted(p for p in Path(runs_dir).iterdir() if p.is_dir())]


# ---- batch record ----------------------------------------------------------------------------------------------------

def _run_id_of(att: Mapping[str, Any], batch_dir: Path) -> Optional[str]:
    """The run directory an attempt created: batch.json's run_dir, else the runner's 'run dir:' line in its log."""
    rd = att.get("run_dir")
    if not rd:
        log = batch_dir / (att.get("log") or f"{att['index']:02d}-{att['scenario']}-{att['repeat']}.txt")
        try:
            with open(log, encoding="utf-8") as f:
                rd = next((line[len("run dir:"):].strip() for line in f if line.startswith("run dir:")), None)
        except OSError:
            rd = None
    return str(rd).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if rd else None


def reconcile(rec: Mapping[str, Any], record_path: Path, runs: Sequence[RunRecord]) -> BatchView:
    """Match every planned attempt of the batch record with its run directory and give it a fate."""
    status = rec.get("status")
    state = rec.get("state") or STATE_BY_STATUS.get(status, f"status {status}")
    atts = sorted(rec["attempts"], key=lambda a: a["index"])
    abort_index, abort_reason = rec.get("abort_index"), rec.get("abort_reason")
    if state == "aborted" and abort_index is None:  # older records: the attempt that exited 31
        first = next((a for a in atts if a.get("exit") == 31), None)
        if first is not None:
            abort_index = first["index"]
            abort_reason = abort_reason or (f"attempt {first['index']} ({first['scenario']}, repeat {first['repeat']}): "
                                            "runner exit 31: a cancel or stop was not confirmed")
    by_name = {r.run_id: r for r in runs}
    rows: List[AttemptRow] = []
    records: List[RunRecord] = []
    claimed = set()
    for a in atts:
        rc, note = a.get("exit"), str(a.get("note") or "")
        run_id = _run_id_of(a, record_path.parent)
        started = rc is not None or note == "running"
        run = by_name.get(run_id) if run_id else None
        if run is not None:
            claimed.add(run_id)
        if not started:
            fate = (f"not run ({note.split(':', 1)[1].strip()})" if note.startswith("not run:")
                    else "not run (the batch record ends before it)")
        elif rc is None:
            fate = "started; no exit recorded (the batch record ends during this attempt)"
        else:
            fate = f"ran (runner exit {rc})" if run is not None else f"no run dir (runner exit {rc})"
            fate += "; aborted the batch" if a["index"] == abort_index else "; interrupted" if rc == 20 else ""
        rows.append(AttemptRow(a["index"], a["scenario"], a["repeat"], rc, a.get("wall_s"), run_id, fate))
        if run is not None:
            records.append(dataclasses.replace(run, runner_exit=rc))
        elif started:
            where = (f"run directory {run_id} not found under runs/" if run_id else
                     "no run directory was created" if rc is not None else "no run directory was found")
            records.append(_placeholder(f"attempt {a['index']:02d} ({a['scenario']}, repeat {a['repeat']})",
                                        record_path.parent / "runs" / "-", a["scenario"],
                                        f"{fate}: {where}", runner_exit=rc))
    unclaimed = [r.run_id for r in runs if r.run_id not in claimed]
    return BatchView(str(record_path), state, status, rec.get("stopped_by"), abort_reason, rows, records, unclaimed)


# ---- numbers ---------------------------------------------------------------------------------------------------------

def summarize(runs: List[RunRecord], batch: Optional[BatchView] = None) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[RunRecord]] = OrderedDict()
    planned = {a.scenario for a in batch.attempts} if batch else set()
    for name in SCENARIO_ORDER + sorted(({r.scenario for r in runs} | planned) - set(SCENARIO_ORDER)):
        members = [r for r in runs if r.scenario == name]
        if members or name in planned:
            groups[name] = members
    out: Dict[str, Dict[str, Any]] = OrderedDict()
    for name, rs in groups.items():
        success = [r for r in rs if r.outcome == "reached" and r.validation == "pass"]
        timed = [r.accept_to_result_sim_s for r in success if r.accept_to_result_sim_s is not None]
        measured = [r.collisions for r in rs if r.collisions is not None]
        out[name] = {
            "attempts": len(rs),
            "not_run": sum(1 for a in batch.attempts if a.scenario == name and a.fate.startswith("not run"))
            if batch else None,
            "validation": dict(Counter(r.validation for r in rs)),
            "outcome": dict(Counter(r.outcome for r in rs)), "safety": dict(Counter(r.safety for r in rs)),
            "data": dict(Counter(r.data for r in rs)),
            "mean_accept_to_result_sim_s_success_only": round(statistics.mean(timed), 2) if timed else None,
            "mean_basis": f"reached + validation pass: {len(success)} of {len(rs)} runs "
                          f"(mean over {len(timed)} with a time)",
            "max_arrival_error_m": max((r.arrival_error_m for r in rs if r.arrival_error_m is not None), default=None),
            "collisions": sum(measured) if measured else None,
            "collisions_measured_runs": len(measured),
            "runs_with_nav2_recoveries": sum(1 for r in rs if r.recoveries),
            "max_reset_error_m": max((r.reset_error_m for r in rs if r.reset_error_m is not None), default=None),
        }
    return out


def summary_json(runs: List[RunRecord], batch: Optional[BatchView]) -> Dict[str, Any]:
    head = None if batch is None else {
        "record": batch.record, "state": batch.state, "status": batch.status, "stopped_by": batch.stopped_by,
        "abort_reason": batch.abort_reason, "planned": batch.planned, "ran": batch.ran, "not_run": batch.not_run}
    return {"batch": head, "attempts": [dataclasses.asdict(a) for a in batch.attempts] if batch else None,
            "unclaimed_run_dirs": batch.unclaimed if batch else [], "scenarios": summarize(runs, batch)}


# ---- page ------------------------------------------------------------------------------------------------------------

def _counts(d: Dict[str, int]) -> str:
    return html.escape(", ".join(f"{k} {v}" for k, v in d.items()))


def _commits(runs: List[RunRecord]) -> str:
    """Every (commit, dirty) pair in the batch with its run count; a batch can span commits."""
    seen = Counter((r.manifest.get("git", {}).get("commit"), r.manifest.get("git", {}).get("dirty_tracked_files"))
                   for r in runs)
    return "; ".join(f"<code>{_fmt(c)}</code> (dirty tracked files: {_fmt(dirty)}; {n} run{'s' if n != 1 else ''})"
                     for (c, dirty), n in seen.items())


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "-"
    return f"{v:.{nd}f}" if isinstance(v, float) else html.escape(str(v))


def _collisions_cell(st: Mapping[str, Any]) -> str:
    n, k = st["attempts"], st["collisions_measured_runs"]
    if k == 0:
        return f"not measured<br><small>0 of {n} runs measured</small>"
    if k == n:
        return str(st["collisions"])
    return f"{st['collisions']}<br><small>{k} of {n} runs measured</small>"


def _trajectory(run: RunRecord) -> List[tuple]:
    pts = []
    try:
        with open(run.path / "trajectory.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("source", "").startswith("sim_state_odom_plus_spawn"):
                    pts.append((float(row["x"]), float(row["y"])))
    except (OSError, ValueError, KeyError):
        return []
    return pts[:: max(1, len(pts) // 400)]


def _map_svg(runs: List[RunRecord]) -> str:
    """Inline SVG: the pinned warehouse map (if readable) and each run's AMCL-independent trajectory."""
    colors = {"normal": "#1f77b4", "bypass": "#2ca02c", "unreachable": "#d62728"}
    paths = {r.run_id: _trajectory(r) for r in runs}
    pts = [p for ps in paths.values() for p in ps] + [(-6.0, -1.0), (0.0, -1.0), (-10.05, -1.0)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs) - 2, max(xs) + 2, min(ys) - 3, max(ys) + 3
    parts = [f'<svg viewBox="{x0} {-y1} {x1 - x0} {y1 - y0}" width="100%" style="max-height:420px;background:#fff" '
             f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="trajectories">']
    png = VENDOR_MAP / "carter_warehouse_navigation.png"
    if png.exists():
        data = base64.b64encode(png.read_bytes()).decode()
        # map: 480 x 776 px, 0.05 m/px, origin (-11.975, -17.975); image row 0 is the top (largest y)
        parts.append(f'<image href="data:image/png;base64,{data}" x="-11.975" y="{-(-17.975 + 776 * 0.05)}" '
                     f'width="{480 * 0.05}" height="{776 * 0.05}" opacity="0.55" preserveAspectRatio="none"/>')
    for r in runs:
        ps = paths[r.run_id]
        if len(ps) > 1:
            d = " ".join(f"{x:.3f},{-y:.3f}" for x, y in ps)
            parts.append(f'<polyline points="{d}" fill="none" stroke="{colors.get(r.scenario, "#555")}" '
                         f'stroke-width="0.06" opacity="0.8"><title>{html.escape(r.run_id)}</title></polyline>')
    for (gx, gy), label in (((0.0, -1.0), "goal"), ((-10.05, -1.0), "unreachable goal"), ((-6.0, -1.0), "spawn")):
        parts.append(f'<circle cx="{gx}" cy="{-gy}" r="0.18" fill="none" stroke="#000" stroke-width="0.05">'
                     f'<title>{label}</title></circle>')
    parts.append("</svg>")
    return "".join(parts)


def _banner(batch: Optional[BatchView]) -> str:
    if batch is None:
        return ("<p class='banner warn'>No batch record (batch.json) was found: the attempts below are the run "
                "directories found under runs/, and planned attempts that left no run directory cannot be listed.</p>")
    counts = f"{batch.ran} of {batch.planned} planned attempts ran; {batch.not_run} not run."
    no_dir = sum(1 for a in batch.attempts if a.fate.startswith("no run dir"))
    counts += f" {no_dir} left no run directory." if no_dir else ""
    if batch.state == "completed":
        text, cls = f"Batch completed: {counts}", "ok"
    elif batch.state == "aborted":
        text, cls = f"Batch aborted: {batch.abort_reason or 'reason not recorded'}. {counts}", "bad"
    elif batch.state == "interrupted":
        text, cls = (f"Batch interrupted by {batch.stopped_by or 'an unrecorded signal'}: the attempt in progress "
                     f"closed out, then the batch stopped. {counts}"), "warn"
    elif batch.state == "running":
        text, cls = ("Batch did not finish: its record still says running, so the batch process ended without "
                     f"closing out (killed?). {counts}"), "bad"
    else:
        text, cls = f"Batch {batch.state}: {counts}", "bad"
    if batch.unclaimed:
        text += f" {len(batch.unclaimed)} run director{'ies' if len(batch.unclaimed) != 1 else 'y'} under runs/ " \
                "not claimed by any attempt (listed below, not counted)."
    return f"<p class='banner {cls}'>{html.escape(text)} <small>Record: {html.escape(batch.record)}</small></p>"


def _attempts_table(batch: Optional[BatchView]) -> str:
    if batch is None:
        return ""
    rows = "".join(f"<tr class='{'ok' if a.fate.startswith('ran (runner exit 0)') else 'warn'}'><td>{a.index}</td>"
                   f"<td>{html.escape(a.scenario)}</td><td>{a.repeat}</td><td>{_fmt(a.exit)}</td>"
                   f"<td>{_fmt(a.wall_s, 1)}</td><td>{_fmt(a.run_id)}</td><td>{html.escape(a.fate)}</td></tr>"
                   for a in batch.attempts)
    unclaimed = "".join(f"<li>{html.escape(n)}</li>" for n in batch.unclaimed)
    extra = (f"<p>Run directories under runs/ not claimed by any attempt of this batch (not counted):</p>"
             f"<ul>{unclaimed}</ul>") if unclaimed else ""
    return (f"<h2>Batch attempts</h2><table><tr><th>#</th><th>scenario</th><th>repeat</th><th>runner exit</th>"
            f"<th>wall s</th><th>run</th><th>fate</th></tr>{rows}</table>{extra}")


def render_html(runs: List[RunRecord], title: str, batch: Optional[BatchView] = None) -> str:
    s = summarize(runs, batch)
    m = next((r.manifest for r in runs if r.manifest), {})
    ver = m.get("versions", {})
    rows = []
    for name, st in s.items():
        rows.append(f"<tr><th>{html.escape(name)}</th><td>{st['attempts']}</td><td>{_fmt(st['not_run'])}</td>"
                    f"<td>{_counts(st['validation'])}</td>"
                    f"<td>{_counts(st['outcome'])}</td><td>{_counts(st['safety'])}</td><td>{_counts(st['data'])}</td>"
                    f"<td>{_fmt(st['mean_accept_to_result_sim_s_success_only'], 2)} s<br><small>{st['mean_basis']}"
                    f"</small></td><td>{_fmt(st['max_arrival_error_m'])} m</td><td>{_collisions_cell(st)}</td>"
                    f"<td>{st['runs_with_nav2_recoveries']}</td>"
                    f"<td>{_fmt(st['max_reset_error_m'], 4)} m</td></tr>")
    detail = []
    for name in s:
        for r in (x for x in runs if x.scenario == name):
            cls = {"pass": "ok", "fail": "bad"}.get(r.validation, "warn")
            detail.append(f"<tr class='{cls}'><td>{html.escape(r.run_id)}</td><td>{html.escape(name)}</td>"
                          f"<td>{_fmt(r.runner_exit)}</td>"
                          f"<td>{html.escape(r.validation)}</td><td>{html.escape(r.outcome)}</td><td>{html.escape(r.safety)}"
                          f"</td><td>{html.escape(r.data)}</td><td>{_fmt(r.nav2_status)} / {_fmt(r.nav2_error_code)}</td>"
                          f"<td>{_fmt(r.arrival_error_m)}</td><td>{_fmt(r.accept_to_result_sim_s, 2)}</td>"
                          f"<td>{'not measured' if r.collisions is None else r.collisions}</td>"
                          f"<td>{_fmt(r.recoveries)}</td>"
                          f"<td>{_fmt(r.reset_error_m, 4)}</td></tr>")
    failures = [f"<li><b>{html.escape(r.run_id)}</b> ({html.escape(r.validation)}): "
                f"{html.escape('; '.join(r.reasons) or 'no reason recorded')}</li>"
                for r in runs if r.validation != "pass"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:system-ui,sans-serif;margin:16px;max-width:1100px}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}}tr.ok td{{background:#eef8ee}}
tr.bad td{{background:#fbeaea}}tr.warn td{{background:#fff7e0}}small{{color:#555}}.note{{color:#555}}
.banner{{padding:8px 10px;border:1px solid #ccc}}.banner.ok{{background:#eef8ee}}.banner.bad{{background:#fbeaea}}
.banner.warn{{background:#fff7e0}}</style></head><body>
<h1>{html.escape(title)}</h1>
{_banner(batch)}
<p class="note">Engineering trial of {len(runs)} attempts; not a navigation performance claim. Each scenario is reported as its own
group; there is no merged success rate. Times are simulation seconds from goal acceptance to Nav2's result, averaged over
successful runs only (task outcome reached and validation pass). Collisions are counted only over runs whose contacts were
measured; "not measured" is never read as zero. A result without the D3 evaluator verdict is shown as "{NOT_EVALUATED}",
never as pass. The final distance to the goal uses the sim_control ground truth. Every run starts with a
sim_control reset whose ground-truth distance to the spawn is shown (reset evidence).</p>
<p>Commits: {_commits(runs)}.<br>
Isaac Sim {_fmt(ver.get('isaac_sim'))}, Nav2 {_fmt(ver.get('navigation2'))}, ROS {_fmt(ver.get('ros_distro'))}.</p>
<h2>Per scenario</h2><table><tr><th>scenario</th><th>attempts</th><th>not run</th><th>validation</th><th>task outcome</th>
<th>safety</th><th>data</th><th>mean time (success only)</th><th>max final distance to goal (ground truth)</th>
<th>collisions</th><th>runs with Nav2 recoveries</th><th>max reset error</th></tr>
{''.join(rows)}</table>
{_attempts_table(batch)}
<h2>Trajectories</h2>{_map_svg(runs)}
<p class="note">Trajectory source: each run's spawn pose plus ideal odometry (trajectory.csv rows
"sim_state_odom_plus_spawn", map frame, independent of AMCL). This is not the sim_control ground truth, which the page
uses only for the final distance to the goal and the reset check.</p>
<h2>Failure and inconclusive cases</h2><ul>{''.join(failures) or '<li>none</li>'}</ul>
<h2>All attempts</h2><table><tr><th>run</th><th>scenario</th><th>runner exit</th><th>validation</th><th>outcome</th>
<th>safety</th><th>data</th><th>Nav2 status / error</th><th>final distance to goal (m, ground truth)</th>
<th>accept to result (sim s)</th><th>collisions</th><th>Nav2 recoveries</th><th>reset error (m)</th></tr>
{''.join(detail)}</table></body></html>"""


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RoboSim Eval D4 batch report")
    p.add_argument("runs_dir")
    p.add_argument("--batch-json", help="the batch record (default: <runs_dir>/../batch.json when it exists)")
    p.add_argument("--title", default="RoboSim Eval batch report")
    a = p.parse_args(argv)
    runs_dir = Path(a.runs_dir)
    if not runs_dir.is_dir():
        print(f"not a directory: {runs_dir}", file=sys.stderr)
        return 2
    record_path = Path(a.batch_json) if a.batch_json else runs_dir.parent / "batch.json"
    rec = _load(record_path) if a.batch_json or record_path.exists() else None
    if (a.batch_json or record_path.exists()) and (rec is None or not isinstance(rec.get("attempts"), list)):
        print(f"batch record unreadable or without attempts: {record_path}", file=sys.stderr)
        return 2
    found = load_runs(runs_dir)
    batch = reconcile(rec, record_path, found) if rec is not None else None
    runs = batch.records if batch else found
    if not runs and not (batch and batch.attempts):
        print(f"no run directories in {runs_dir} and no batch record", file=sys.stderr)
        return 2
    out = runs_dir / "report.html"
    out.write_text(render_html(runs, a.title, batch), encoding="utf-8")
    (runs_dir / "summary.json").write_text(json.dumps(summary_json(runs, batch), indent=2), encoding="utf-8")
    print(f"written {out} ({len(runs)} attempts" + (f" of {batch.planned} planned" if batch else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
