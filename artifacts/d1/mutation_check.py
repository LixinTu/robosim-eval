"""Mutation check for the D1 doctor rules: break one rule at a time (in memory only) and confirm a fixed-input test
catches it. Run from the repo root in WSL:  python3 artifacts/d1/mutation_check.py
Exit 0 = the baseline passes and every mutation is caught by at least one test; 1 otherwise.
"""
from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / "robosim_eval" / "doctor_checks.py").read_text(encoding="utf-8")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

MUTATIONS: Dict[str, List[str]] = {  # name -> [original, replacement]
    "M1 stale streams never flagged": ["elif last_age is not None and last_age > th.max_age_s:", "elif False:"],
    "M2 slow streams never flagged": ["elif rate < th.min_rate_hz:", "elif False:"],
    "M3 missing publisher treated as silent": ["    if not so.present:\n", "    if False:\n"],
    "M4 clock stall ignored": ["if clock.last_age_s is not None and clock.last_age_s > thresholds.clock_stall_s:",
                               "if False:"],
    "M5 frozen clock counts as progress": ["        if b > a:\n            progress += b - a",
                                           "        if b >= a:\n            progress += b - a + 0.01"],
    "M6 environment errors ignored": ["    if env_reasons:\n", "    if False:\n"],
    "M7 backward clock jumps counted as progress": ["        elif b < a:\n            backward += 1",
                                                    "        elif b < a:\n            progress += a - b"],
}


def run_tests(source: str) -> List[str]:
    """Load `source` as robosim_eval.doctor_checks, re-import the tests, run every test_* function; return failures."""
    import robosim_eval  # noqa: F401  (parent package must exist in sys.modules)
    mod = types.ModuleType("robosim_eval.doctor_checks")
    mod.__file__ = "<mutant>"
    sys.modules["robosim_eval.doctor_checks"] = mod
    exec(compile(source, "<mutant doctor_checks>", "exec"), mod.__dict__)
    sys.modules.pop("test_doctor_checks", None)
    tests = importlib.import_module("test_doctor_checks")
    failed = []
    for name in sorted(n for n in dir(tests) if n.startswith("test_")):
        try:
            getattr(tests, name)()
        except Exception:  # an assertion or any error means the mutant was detected by this test
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
