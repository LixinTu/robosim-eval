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
        "        if x.preset_unreachable:\n            missing = _unreachable_missing(",
        "        if True:\n            missing = _unreachable_missing("],
    # review round 2 (eval-1, eval-6..eval-11, runner-9, simctl-2, doctor_config-10)
    "M9 unreachable without complete data": ["    if not data_complete:\n        missing.append(",
                                             "    if False:\n        missing.append("],
    "M10 unreachable although ground truth reached the goal": ["    elif err <= x.tolerance_m:\n",
                                                               "    elif False:\n"],
    "M11 required backward stamps ignored": [
        "    other += [f\"{n}: {c} backward stamps\" for n, c in x.required_backward.items() if c]\n", ""],
    "M12 CANCELED read as canceled without a cancel request": [
        "    elif x.cancel_requested and x.terminal_status == 5 and x.cancel_reason in (\"interrupt\", \"injected\"):\n",
        "    elif x.terminal_status == 5:\n"],
    "M13 any abort error code supports unreachable": ["    elif x.error_code not in NO_PATH_ERROR_CODES:\n",
                                                      "    elif False:\n"],
    "M14 unreachable without map evidence": ["    if x.unreachable_evidence is not True:\n", "    if False:\n"],
    "M15 missing ground truth read as not reached": ["    if arrival_problem:\n        missing.append(",
                                                     "    if False:\n        missing.append("],
    "M16 terminal status accepted without a confirmed stop": [
        "    if x.terminal_status is not None and not x.stop_confirmed:", "    if x.terminal_status == 4 and False:"],
    "M17 lost contact events ignored": ["    elif x.contacts_dropped:\n", "    elif False:\n"],
    "M18 recording coverage problems ignored": ["    other: List[str] = list(x.coverage_problems)\n",
                                                "    other: List[str] = []\n"],
    "M19 non-finite arrival error accepted": ["    if not math.isfinite(err):\n", "    if False:\n"],
    "M20 non-finite tolerance accepted": ["    if not _finite(x.tolerance_m) or x.tolerance_m <= 0:\n",
                                          "    if False:\n"],
    "M21 expected collision not required": [
        "    if expect_safety == \"fail\" and safety == \"pass\":\n", "    if False:\n"],
    "M22 any incomplete data satisfies an expected dropout": [
        "(expect_data == \"incomplete\" and bool(gap_problems) and not other_problems)",
        "(expect_data == \"incomplete\" and not data_complete)"],
}


def run_tests(source: str) -> List[str]:
    importlib.import_module("robosim_eval")  # the package must exist before its evaluator module is replaced
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
