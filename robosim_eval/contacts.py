"""WSL-side access to the Kit contact monitor (robosim_eval/kit/contact_monitor.py) through Windows interop.

The monitor runs inside Isaac Sim through isaacsim.code_editor.python_server (127.0.0.1:8226, token auth; enabled by
start_isaac_ros2.ps1 -PythonServer at the user's decision). WSL cannot reach Windows loopback, so the Windows-side
client scripts/windows/isaac_py.ps1 is started through WSL interop. Call expressions use default arguments only, so
no quoting crosses the Linux/Windows boundary.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Tuple

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
CLIENT = r"D:\RoboSim-Eval\scripts\windows\isaac_py.ps1"
KIT_FILE = r"D:\RoboSim-Eval\robosim_eval\kit\contact_monitor.py"

__all__ = ["ContactError", "install", "fetch", "found_pairs"]


class ContactError(RuntimeError):
    """The contact monitor could not be reached, or it reported an error."""


def _call(expr: str, timeout: float = 90.0) -> Dict[str, Any]:
    try:
        proc = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CLIENT,
                               "-CodeFile", KIT_FILE, "-Call", expr], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContactError(f"isaac_py.ps1 did not run: {exc}") from exc
    lines = [ln.strip().lstrip("\ufeff") for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        resp = json.loads(lines[-1])
    except (IndexError, ValueError) as exc:
        raise ContactError(f"isaac_py.ps1 exit {proc.returncode}: {proc.stdout[-300:]} {proc.stderr[-300:]}") from exc
    if resp.get("status") != "ok":
        raise ContactError(f"python_server error (client exit {proc.returncode}): {resp.get('ename')} "
                           f"{resp.get('evalue')}")
    try:
        return json.loads(resp["result"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContactError(f"unexpected result: {str(resp)[:300]}") from exc


def install() -> Dict[str, Any]:
    """Apply contact reporting to the robot's rigid bodies (default root /World/Nova_Carter_ROS); idempotent."""
    out = _call("robosim_contacts_install()")
    if not out.get("ok"):
        raise ContactError(f"install failed: {out}")
    return out


def fetch() -> Dict[str, Any]:
    """Contact events since the previous fetch (the monitor's buffer is cleared)."""
    out = _call("robosim_contacts_fetch()")
    if not out.get("ok") or not out.get("subscribed"):
        raise ContactError(f"fetch failed or monitor not subscribed: {str(out)[:300]}")
    return out


def found_pairs(fetched: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(actor0, actor1) of every contact that started ('found') in a fetched batch."""
    return [(e["actor0"], e["actor1"]) for e in fetched.get("events", []) if e.get("type") == "found"]
