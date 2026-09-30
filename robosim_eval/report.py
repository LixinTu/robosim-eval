"""D4 batch report: a static HTML page built only from saved run records (plan doc A3 report.py, A6 reporting rules).

  python3 -m robosim_eval.report <batch_dir> [--title T]   ->  <batch_dir>/report.html (exit 0; 2 when no run found)
Rules applied (A6): every attempt is counted, failed and broken ones included; average times are over reached runs
only and say so; each scenario is its own group, so unreachable goals are never merged into a success rate; failure
cases are listed with their reasons; versions, commit and the reset evidence are shown. The 9-run batch is an
engineering trial, not a navigation performance claim (A4), and the page says so.
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import math
import statistics
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

VENDOR_MAP = Path.home() / "robotics/vendor/isaac-ros-6.1/jazzy_ws/src/navigation/carter_navigation/maps"
SCENARIO_ORDER = ["normal", "bypass", "unreachable"]


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
    collisions: int
    manifest: Dict[str, Any] = field(default_factory=dict)


def _load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_runs(batch_dir: Path) -> List[RunRecord]:
    runs = []
    for d in sorted(p for p in Path(batch_dir).iterdir() if p.is_dir()):
        r, m = _load(d / "result.json"), _load(d / "manifest.json") or {}
        scenario = (r or {}).get("runner", {}).get("scenario") or d.name.rsplit("-", 2)[0].split("-")[0]
        if r is None:
            runs.append(RunRecord(d.name, d, scenario, "missing", "unknown", "unknown", "incomplete", "error",
                                  ["result.json missing or unreadable"], [], None, None, None, None, None, None, 0, m))
            continue
        vr = r.get("verdict_reasons") or {}
        ev, tm, nav = r.get("evaluator") or {}, r.get("timing") or {}, r.get("nav2_raw") or {}
        after = ((r.get("runner") or {}).get("ground_truth") or {}).get("after_reset")
        reset_err = math.hypot(after["x"] + 6.0, after["y"] + 1.0) if after else None
        runs.append(RunRecord(
            run_id=d.name, path=d, scenario=scenario, validation=r.get("validation_status", "missing"),
            outcome=r.get("task_outcome", "unknown"), safety=r.get("safety_status", "unknown"),
            data=r.get("data_status", "incomplete"), execution=r.get("execution_status", "error"),
            reasons=list(vr.get("fail", [])) + list(vr.get("inconclusive", [])), warnings=list(vr.get("warnings", [])),
            arrival_error_m=ev.get("arrival_error_m"), accept_to_result_sim_s=tm.get("accept_to_result_sim_s"),
            accept_to_result_wall_s=tm.get("accept_to_result_wall_s"), nav2_status=nav.get("terminal_status_name"),
            nav2_error_code=nav.get("error_code"), reset_error_m=reset_err,
            collisions=len(ev.get("disallowed_contacts") or []), manifest=m))
    return runs


def summarize(runs: List[RunRecord]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[RunRecord]] = OrderedDict()
    for name in SCENARIO_ORDER + sorted({r.scenario for r in runs} - set(SCENARIO_ORDER)):
        members = [r for r in runs if r.scenario == name]
        if members:
            groups[name] = members
    out: Dict[str, Dict[str, Any]] = OrderedDict()
    for name, rs in groups.items():
        reached = [r.accept_to_result_sim_s for r in rs if r.outcome == "reached" and r.accept_to_result_sim_s is not None]
        out[name] = {
            "attempts": len(rs), "validation": dict(Counter(r.validation for r in rs)),
            "outcome": dict(Counter(r.outcome for r in rs)), "safety": dict(Counter(r.safety for r in rs)),
            "data": dict(Counter(r.data for r in rs)),
            "mean_accept_to_result_sim_s_success_only": round(statistics.mean(reached), 2) if reached else None,
            "mean_basis": f"reached runs only ({len(reached)} of {len(rs)})",
            "max_arrival_error_m": max((r.arrival_error_m for r in rs if r.arrival_error_m is not None), default=None),
            "collisions": sum(r.collisions for r in rs),
            "max_reset_error_m": max((r.reset_error_m for r in rs if r.reset_error_m is not None), default=None),
        }
    return out


def _fmt(v: Any, nd: int = 3) -> str:
    if v is None:
        return "-"
    return f"{v:.{nd}f}" if isinstance(v, float) else html.escape(str(v))


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


def render_html(runs: List[RunRecord], title: str) -> str:
    s = summarize(runs)
    m = next((r.manifest for r in runs if r.manifest), {})
    git, ver = m.get("git", {}), m.get("versions", {})
    rows = []
    for name, st in s.items():
        rows.append(f"<tr><th>{html.escape(name)}</th><td>{st['attempts']}</td><td>{_fmt(st['validation'])}</td>"
                    f"<td>{_fmt(st['outcome'])}</td><td>{_fmt(st['safety'])}</td><td>{_fmt(st['data'])}</td>"
                    f"<td>{_fmt(st['mean_accept_to_result_sim_s_success_only'], 2)} s<br><small>{st['mean_basis']}"
                    f"</small></td><td>{_fmt(st['max_arrival_error_m'])} m</td><td>{st['collisions']}</td>"
                    f"<td>{_fmt(st['max_reset_error_m'], 4)} m</td></tr>")
    detail = []
    for name in s:
        for r in (x for x in runs if x.scenario == name):
            cls = {"pass": "ok", "fail": "bad"}.get(r.validation, "warn")
            detail.append(f"<tr class='{cls}'><td>{html.escape(r.run_id)}</td><td>{html.escape(name)}</td>"
                          f"<td>{html.escape(r.validation)}</td><td>{html.escape(r.outcome)}</td><td>{html.escape(r.safety)}"
                          f"</td><td>{html.escape(r.data)}</td><td>{_fmt(r.nav2_status)} / {_fmt(r.nav2_error_code)}</td>"
                          f"<td>{_fmt(r.arrival_error_m)}</td><td>{_fmt(r.accept_to_result_sim_s, 2)}</td>"
                          f"<td>{_fmt(r.reset_error_m, 4)}</td></tr>")
    failures = [f"<li><b>{html.escape(r.run_id)}</b> ({html.escape(r.validation)}): "
                f"{html.escape('; '.join(r.reasons) or 'no reason recorded')}</li>"
                for r in runs if r.validation != "pass"]
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:system-ui,sans-serif;margin:16px;max-width:1100px}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}}tr.ok td{{background:#eef8ee}}
tr.bad td{{background:#fbeaea}}tr.warn td{{background:#fff7e0}}small{{color:#555}}.note{{color:#555}}</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="note">Engineering trial of {len(runs)} attempts; not a navigation performance claim. Each scenario is reported as its own
group; there is no merged success rate. Times are simulation seconds from goal acceptance to Nav2's result, averaged over
reached runs only. Arrival error uses the sim_control ground truth. Every run starts with a sim_control reset whose
ground-truth distance to the spawn is shown (reset evidence).</p>
<p>Commit <code>{_fmt(git.get('commit'))}</code> (dirty tracked files: {_fmt(git.get('dirty_tracked_files'))}),
Isaac Sim {_fmt(ver.get('isaac_sim'))}, Nav2 {_fmt(ver.get('navigation2'))}, ROS {_fmt(ver.get('ros_distro'))}.</p>
<h2>Per scenario</h2><table><tr><th>scenario</th><th>attempts</th><th>validation</th><th>task outcome</th><th>safety</th>
<th>data</th><th>mean time (success only)</th><th>max arrival error</th><th>collisions</th><th>max reset error</th></tr>
{''.join(rows)}</table>
<h2>Trajectories</h2>{_map_svg(runs)}
<h2>Failure and inconclusive cases</h2><ul>{''.join(failures) or '<li>none</li>'}</ul>
<h2>All attempts</h2><table><tr><th>run</th><th>scenario</th><th>validation</th><th>outcome</th><th>safety</th><th>data</th>
<th>Nav2 status / error</th><th>arrival error (m)</th><th>accept to result (sim s)</th><th>reset error (m)</th></tr>
{''.join(detail)}</table></body></html>"""


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="RoboSim Eval D4 batch report")
    p.add_argument("batch_dir")
    p.add_argument("--title", default="RoboSim Eval batch report")
    a = p.parse_args(argv)
    runs = load_runs(Path(a.batch_dir))
    if not runs:
        print(f"no run directories in {a.batch_dir}", file=sys.stderr)
        return 2
    out = Path(a.batch_dir) / "report.html"
    out.write_text(render_html(runs, a.title), encoding="utf-8")
    (Path(a.batch_dir) / "summary.json").write_text(json.dumps(summarize(runs), indent=2), encoding="utf-8")
    print(f"written {out} ({len(runs)} attempts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
