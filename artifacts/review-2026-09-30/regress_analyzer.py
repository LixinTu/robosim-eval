"""Review 2026-09-30 regression check: re-evaluate every real run (in memory, nothing written) with the analyzer in sys.argv[1] and
compare with the analyzer verdict stored in the run's result.json; also report the D3 in-window data check."""
import glob, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "scripts", "wsl"))
sys.path.insert(0, sys.argv[1])
import analyze_attempt as aa
try:
    from robosim_eval.evaluator import integrity_gap
except ImportError:
    def integrity_gap(e):
        return 0.0
import yaml
KEYS = ("execution_status", "task_outcome", "data_status", "validation_status")
changed = 0
dirs = sorted(set(os.path.dirname(os.path.dirname(p)) for p in glob.glob("/mnt/d/RoboSim-Eval/artifacts/**/rosbag/*", recursive=True)))
for d in dirs:
    res_p = os.path.join(d, "result.json")
    if not os.path.exists(res_p):
        continue
    res = json.load(open(res_p))
    stored = res.get("analyzer") or {k: res.get(k) for k in KEYS}
    cfg_p = os.path.join(d, "config.resolved.yaml")
    if os.path.exists(cfg_p):
        c = yaml.safe_load(open(cfg_p))
        g = c["scenario"]["goal"]; sp = c["sim"]["spawn"]
        goal, spawn = (g["x"], g["y"], g["yaw"]), (sp["x"], sp["y"], sp["yaw"])
    else:
        goal = tuple((res.get("goal") or {}).get(k) for k in ("x", "y", "yaw")); spawn = (-6.0, -1.0, 3.141592653589793)
    try:
        bag = aa.read_bag(os.path.join(d, "rosbag"))
        tr = aa.parse_goal_transcript(d)
        new, _ = aa.evaluate(bag, tr, goal, spawn)
    except Exception as e:  # report and continue: this is a scan
        print(f"{os.path.relpath(d, '/mnt/d/RoboSim-Eval/artifacts'):58s} ERROR {type(e).__name__}: {str(e)[:100]}")
        continue
    diff = [k for k in KEYS if stored.get(k) != new[k]]
    integ = res.get("data_integrity") or {}
    in_window_missing = [n for n in ("clock", "odom", "tf_odom_base") if n in integ and integrity_gap(integ[n]) is None and integ[n].get("count")]
    changed += bool(diff)
    print(f"{os.path.relpath(d, '/mnt/d/RoboSim-Eval/artifacts'):58s} {'CHANGED ' + str({k: (stored.get(k), new[k]) for k in diff}) if diff else 'same'}"
          f"{'  D3 in-window missing: ' + str(in_window_missing) if in_window_missing else ''}"
          f"{'  new reasons: ' + str([r for r in new['verdict_reasons']['inconclusive'] if 'goal id' in r or 'position sample' in r or 'evaluation window' in r]) if diff else ''}")
print(f"runs with a changed analyzer verdict: {changed}")
