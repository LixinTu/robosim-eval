"""Mutation check for the D3 evaluator rules: break one rule at a time (in memory only) and confirm a fixed-input test
catches it. Run from the repo root in WSL:  python3 artifacts/d3/mutation_check.py
Exit 0 = the baseline passes and every mutation is caught by at least one test; 1 otherwise.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / "robosim_eval" / "evaluator.py").read_text(encoding="utf-8")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

MUTATIONS: Dict[str, List[str]] = {
    "M1 false success accepted": ["        elif err > x.tolerance_m:\n", "        elif False:\n"],
    "M2 missing contact data treated as safe": ["    if not x.contacts_measured:\n", "    if False:\n"],
    "M3 backward clock ignored": ["    if x.clock_backward_jumps:\n", "    if False:\n"],
    "M4 cancel without acknowledgement ignored": ["    if x.cancel_requested and x.terminal_status is None:\n",
                                                  "    if False:\n"],
    "M5 ground contacts counted as collisions": [
        "        if not any(other.startswith(p) for p in policy.ignore_prefixes):\n", "        if True:\n"],
    "M6 robot self contacts counted": ["        if ra == rb:  # robot self contact, or not involving the robot\n",
                                       "        if not ra and not rb:\n"],
    "M7 informational gaps make data incomplete": [
        "    for name, gap in x.required_gaps.items():\n",
        "    for name, gap in {**x.required_gaps, **x.informational_gaps}.items():\n"],
    "M8 abort read as unreachable without the preset label": [
        "        if x.preset_unreachable and not reached and data_complete:\n",
        "        if not reached and data_complete:\n"],
}


def run_tests(source: str) -> List[str]:
    import robosim_eval  # noqa: F401
    mod = types.ModuleType("robosim_eval.evaluator")
    mod.__file__ = "<mutant>"
    sys.modules["robosim_eval.evaluator"] = mod
    exec(compile(source, "<mutant evaluator>", "exec"), mod.__dict__)
    sys.modules.pop("test_evaluator", None)
    tests = importlib.import_module("test_evaluator")
    failed = []
    for name in sorted(n for n in dir(tests) if n.startswith("test_")):
        try:
            getattr(tests, name)()
        except Exception:  # an assertion or any error means the mutant was detected
            failed.append(name)
    return failed


def main() -> int:
    ok = True
    base = run_tests(SRC)
    print(f"baseline failures: {base}")
    ok &= not base
    for name, (old, new) in MUTATIONS.items():
        if SRC.count(old) != 1:
            print(f"{name}: SETUP ERROR, pattern found {SRC.count(old)} times")
            ok = False
            continue
        caught = run_tests(SRC.replace(old, new))
        print(f"{name} -> caught by {caught if caught else 'NOTHING'}")
        ok &= bool(caught)
    print(f"after restore: {run_tests(SRC)}")
    print(f"result: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
