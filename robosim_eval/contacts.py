"""WSL-side access to the Kit contact monitor (robosim_eval/kit/contact_monitor.py) through Windows interop.

The monitor runs inside Isaac Sim through isaacsim.code_editor.python_server (127.0.0.1:8226, token auth; enabled by
start_isaac_ros2.ps1 -PythonServer at the user's decision). WSL cannot reach Windows loopback, so the Windows-side
client scripts/windows/isaac_py.ps1 is started through WSL interop. Call expressions use default arguments only, so
no quoting crosses the Linux/Windows boundary.

Every failure of this channel is a ContactError, including undecodable client output: powershell.exe writes in the
console code page (GBK/CP936 on this zh-CN machine) or UTF-16, so its output is read as bytes and decoded leniently.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

__all__ = ["ContactError", "install", "fetch", "found_pairs", "windows_path"]


def windows_path(path: PurePosixPath) -> Optional[str]:
    """Windows form of a WSL path on a Windows drive (/mnt/d/x -> D:\\x); None for any other path."""
    parts = path.parts
    drive = parts[2] if len(parts) >= 3 and parts[:2] == ("/", "mnt") else ""
    if len(drive) != 1 or not (drive.isascii() and drive.isalpha()):
        return None
    return drive.upper() + ":\\" + "\\".join(parts[3:])


REPO = Path(__file__).resolve().parents[1]
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
# the client and the Kit file of the checkout this module is in (D:\RoboSim-Eval\... for the main checkout)
CLIENT = windows_path(REPO / "scripts" / "windows" / "isaac_py.ps1")
KIT_FILE = windows_path(REPO / "robosim_eval" / "kit" / "contact_monitor.py")


class ContactError(RuntimeError):
    """The contact monitor could not be reached, or it reported an error."""


def _decode(data: bytes) -> str:
    """Text of powershell.exe output: UTF-16 (BOM or NUL bytes), UTF-8, else the zh-CN console code page (GBK).

    Never raises: bytes that fit none of them are replaced, so the caller can still report them.
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if b"\x00" in data:  # UTF-16LE without a BOM; PowerShell text output never contains NUL otherwise
        return data.decode("utf-16-le", errors="replace")
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _call(expr: str, timeout: float = 90.0) -> Dict[str, Any]:
    if CLIENT is None or KIT_FILE is None:
        raise ContactError(f"the checkout {REPO} is not on a Windows drive (/mnt/<drive>/...), so the Windows client "
                           f"cannot run its isaac_py.ps1")
    try:
        proc = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", CLIENT,
                               "-CodeFile", KIT_FILE, "-Call", expr], capture_output=True, timeout=timeout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ContactError(f"isaac_py.ps1 did not run: {exc}") from exc
    stdout, stderr = _decode(proc.stdout), _decode(proc.stderr)
    lines = [ln.strip().lstrip("\ufeff") for ln in stdout.splitlines() if ln.strip()]
    try:
        resp = json.loads(lines[-1])
    except (IndexError, ValueError) as exc:
        raise ContactError(f"isaac_py.ps1 exit {proc.returncode}: {stdout[-300:]} {stderr[-300:]}") from exc
    if not isinstance(resp, dict):
        raise ContactError(f"isaac_py.ps1 exit {proc.returncode}: reply is not a JSON object: {lines[-1][:300]}")
    if resp.get("status") != "ok":
        raise ContactError(f"python_server error (client exit {proc.returncode}): {resp.get('ename')} "
                           f"{resp.get('evalue')} {stderr[-300:]}".rstrip())
    try:
        out = json.loads(resp["result"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContactError(f"unexpected result: {str(resp)[:300]}") from exc
    if not isinstance(out, dict):
        raise ContactError(f"unexpected result (not a JSON object): {str(resp)[:300]}")
    return out


def install() -> Dict[str, Any]:
    """Apply contact reporting to the robot's rigid bodies (default root /World/Nova_Carter_ROS); idempotent."""
    out = _call("robosim_contacts_install()")
    if not out.get("ok"):
        raise ContactError(f"install failed: {out}")
    return out


def _persist_pairs(counts: Any) -> List[List[str]]:
    """[actor0, actor1] of every persist_counts key "actor0|actor1" (USD paths cannot contain '|')."""
    if not isinstance(counts, dict):
        raise ContactError(f"fetch: persist_counts is not an object: {str(counts)[:300]}")
    pairs = []
    for key in counts:
        a0, sep, a1 = str(key).partition("|")
        if not (sep and a0 and a1):
            raise ContactError(f"fetch: malformed persist_counts key {key!r}")
        pairs.append([a0, a1])
    return pairs


def fetch() -> Dict[str, Any]:
    """Contact events since the previous fetch (the monitor's buffer is cleared).

    Besides the monitor's own fields the result carries 'persist_pairs' ([actor0, actor1] of every pair still in contact
    during the batch, from persist_counts) and 'dropped' (FOUND/LOST events lost at the monitor's buffer cap). Both are
    completeness signals, so a reply without them, or with malformed events, is a ContactError: the caller must not
    read missing data as "no contact".
    """
    out = _call("robosim_contacts_fetch()")
    if not out.get("ok") or not out.get("subscribed"):
        raise ContactError(f"fetch failed or monitor not subscribed: {str(out)[:300]}")
    dropped, events = out.get("dropped"), out.get("events")
    if not isinstance(dropped, int) or isinstance(dropped, bool) or dropped < 0:
        raise ContactError(f"fetch: 'dropped' missing or not a count: {dropped!r}")
    if not isinstance(events, list) or not all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("type", "actor0", "actor1"))
            for e in events):
        raise ContactError(f"fetch: 'events' missing or malformed: {str(events)[:300]}")
    out["persist_pairs"] = _persist_pairs(out.get("persist_counts"))
    return out


def found_pairs(fetched: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(actor0, actor1) of every contact in a fetched batch: each 'found' event, then each persisting pair not already
    found in the batch (a contact that started before the pre-run clear only persists during the run).

    PhysX reports a pair when either body has contact reporting, which the monitor enables on the robot's bodies only
    (an asset could enable it itself); the evaluator's ContactPolicy drops pairs without a robot body, robot self
    contacts and the ignored ground contacts.
    """
    pairs = [(e["actor0"], e["actor1"]) for e in fetched.get("events", []) if e.get("type") == "found"]
    seen = {frozenset(p) for p in pairs}
    for a0, a1 in fetched.get("persist_pairs", []):
        if frozenset((a0, a1)) not in seen:
            seen.add(frozenset((a0, a1)))
            pairs.append((a0, a1))
    return pairs
