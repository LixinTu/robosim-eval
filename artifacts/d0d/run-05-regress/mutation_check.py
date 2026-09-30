"""Mutation check: break one rule at a time and confirm that the fixed-input tests catch it."""
import importlib, sys, os, types, traceback
sys.path.insert(0, "/mnt/d/RoboSim-Eval/scripts/wsl"); sys.path.insert(0, "/mnt/d/RoboSim-Eval/tests")
import analyze_attempt as aa
import test_analyze_attempt as T

def run_all():
    failed = []
    for name in sorted(n for n in dir(T) if n.startswith("test_")):
        fn = getattr(T, name)
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                import tempfile, pathlib
                with tempfile.TemporaryDirectory() as d: fn(pathlib.Path(d))
            else:
                fn()
        except Exception:
            failed.append(name)
    return failed

print("baseline failures:", run_all())
orig_stop, orig_eval_src = aa.stop_still, None

# M1: stop-still always "confirmed"
aa.stop_still = lambda odom, t, *a, **k: {**orig_stop(odom, t, *a, **k), "state": "confirmed", "confirmed_at_t_ns": t, "confirmed_at_sim": 0.0}
print("M1 stop always confirmed ->", run_all()); aa.stop_still = orig_stop

# M2: ignore goal-id filtering by making every status belong to the transcript goal
orig_evaluate = aa.evaluate
def eval_nofilter(bag, tr, *a, **k):
    bag = dict(bag); tid = tr.get("goal_id") or "aa" * 16
    bag["status"] = [(t, tid, s) for t, u, s in bag["status"]]
    return orig_evaluate(bag, tr, *a, **k)
T.aa.evaluate = eval_nofilter
print("M2 no goal-id filter ->", run_all()); T.aa.evaluate = orig_evaluate

# M3: treat ABORTED like SUCCEEDED
def eval_abort_ok(bag, tr, *a, **k):
    bag = dict(bag); bag["status"] = [(t, u, 4 if s == 6 else s) for t, u, s in bag["status"]]
    return orig_evaluate(bag, tr, *a, **k)
T.aa.evaluate = eval_abort_ok
print("M3 aborted counted as succeeded ->", run_all()); T.aa.evaluate = orig_evaluate

# M4: data integrity check disabled
orig_int = aa.stream_integrity
aa.stream_integrity = lambda seq, lo, hi, stamp_index=1: {"count": len(seq), "count_in_window": len(seq), "max_wall_gap_s": 0.0, "backward_stamps": 0}
print("M4 integrity disabled ->", run_all()); aa.stream_integrity = orig_int
print("after restore:", run_all())
