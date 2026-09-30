"""Fake process table for the shell-script tests: stands in for /proc, pgrep, pkill, kill and setsid.

The scripts under test read process facts from $ROBOSIM_PROC_ROOT (stat, cmdline, environ, boot_id) and signal through
pgrep/pkill/`env kill`, which the tests replace with stubs that call this module. Nothing here ever signals a real
process: delivering a signal only edits files under $ROBOSIM_PROC_ROOT and appends a line to signals.log next to it.

Per fake process <root>/<pid>/:
  stat, cmdline, environ   the /proc formats the scripts parse (starttime = stat field 22, session = field 6)
  fake.json                behaviour: dies_on (signals that end it; KILL always does), exit_on (exit status per signal,
                           default 128 + signal number), follows (it exits by itself once all these pids are gone, like a
                           wrapper whose child ended), status (its exit status then), on_exit ([path, template] files
                           written when it exits by itself; "{status:<pid>}" is replaced by that pid's exit status)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

SIGNALS = {"HUP": 1, "INT": 2, "KILL": 9, "TERM": 15}
FIRST_FAKE_PID = 5000001  # above the kernel's PID_MAX_LIMIT (4194304): no real process can have these ids


def root() -> Path:
    return Path(os.environ["ROBOSIM_PROC_ROOT"])


def log_signal(line: str) -> None:
    with open(root().parent / "signals.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def next_counter(name: str, start: int) -> int:
    path = root() / f".{name}"
    value = int(path.read_text()) + 1 if path.exists() else start
    path.write_text(str(value))
    return value


def live_pids() -> List[int]:
    return sorted(int(p.name) for p in root().iterdir() if p.name.isdigit() and (p / "stat").exists())


def stat_fields(pid: int) -> List[str]:
    text = (root() / str(pid) / "stat").read_text()
    return text[text.rindex(") ") + 2:].split()  # [state, ppid, pgrp, session, ..., starttime at index 19]


def session_of(pid: int) -> int:
    return int(stat_fields(pid)[3])


def ppid_of(pid: int) -> int:
    return int(stat_fields(pid)[1])


def cmdline_of(pid: int) -> str:
    return (root() / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode().strip()


def behaviour(pid: int) -> Dict:
    path = root() / str(pid) / "fake.json"
    return json.loads(path.read_text()) if path.exists() else {}


def dead() -> Dict[str, int]:
    path = root() / ".dead.json"
    return json.loads(path.read_text()) if path.exists() else {}


def mark_dead(pid: int, status: int) -> None:
    d = dead()
    d[str(pid)] = status
    (root() / ".dead.json").write_text(json.dumps(d))
    shutil.rmtree(root() / str(pid))


def make(pid: int, sid: int, ppid: int, start: int, argv: List[str], env: Dict[str, str], beh: Dict,
         comm: Optional[str] = None) -> None:
    d = root() / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    comm = comm or Path(argv[0]).name[:15]
    rest = ["S", ppid, sid, sid, 0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 20, 0, 1, 0, start, 0, 0]
    (d / "stat").write_text(f"{pid} ({comm}) " + " ".join(str(v) for v in rest) + "\n")
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    (d / "environ").write_bytes(b"".join(f"{k}={v}".encode() + b"\0" for k, v in env.items()))
    (d / "fake.json").write_text(json.dumps(beh))


def cascade() -> None:
    """Processes that follow others exit by themselves once everything they follow is gone (writing on_exit)."""
    changed = True
    while changed:
        changed = False
        alive = set(live_pids())
        for pid in sorted(alive):
            beh = behaviour(pid)
            follows = beh.get("follows") or []
            if follows and not any(p in alive for p in follows):
                status = int(beh.get("status", 0))
                statuses = dead()
                for path, template in beh.get("on_exit", []):
                    text = re.sub(r"\{status:(\d+)\}", lambda m: str(statuses.get(m.group(1), "")), template)
                    Path(path).write_text(text + "\n")
                mark_dead(pid, status)
                changed = True
                break


def deliver(pid: int, sig: str) -> None:
    beh = behaviour(pid)
    if sig == "KILL" or sig in beh.get("dies_on", []):
        mark_dead(pid, int(beh.get("exit_on", {}).get(sig, 128 + SIGNALS[sig])))
        cascade()


def parse_sig(arg: str) -> str:
    name = arg.lstrip("-").upper().removeprefix("SIG")
    return {str(v): k for k, v in SIGNALS.items()}.get(name, name)


def cmd_pgrep(args: List[str]) -> int:
    sid = ppid = pattern = None
    full_line = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-s":
            sid, i = args[i + 1], i + 2
            continue
        if a == "-P":
            ppid, i = int(args[i + 1]), i + 2
            continue
        if a in ("-a", "-af", "-fa"):
            full_line = True
        if a in ("-f", "-af", "-fa", "-a"):
            i += 1
            continue
        pattern, i = a, i + 1
    if sid is not None:
        if sid in os.environ.get("FAKE_PGREP_FAIL", "").split(","):
            print("pgrep: fake query failure", file=sys.stderr)
            return 3
        if not sid.isdigit():
            print(f"pgrep: invalid session id '{sid}'", file=sys.stderr)
            return 2
    hits = []
    for pid in live_pids():
        if sid is not None and session_of(pid) != int(sid):
            continue
        if ppid is not None and ppid_of(pid) != ppid:
            continue
        if pattern is not None and not re.search(pattern, cmdline_of(pid)):
            continue
        hits.append(pid)
    for pid in hits:
        print(f"{pid} {cmdline_of(pid)}" if full_line else pid)
    return 0 if hits else 1


def cmd_pkill(args: List[str]) -> int:
    sig = parse_sig(args[0])
    assert args[1] == "-s", f"fake pkill supports only -SIG -s <sid>, got {args}"
    sid = int(args[2])
    targets = [p for p in live_pids() if session_of(p) == sid]
    log_signal(f"pkill {sig} session {sid} -> {' '.join(map(str, targets)) or 'none'}")
    for pid in targets:
        if (root() / str(pid)).exists():
            deliver(pid, sig)
    return 0 if targets else 1


def cmd_kill(args: List[str]) -> int:
    sig = parse_sig(args[0]) if args[0].startswith("-") else "TERM"
    pids = [int(a) for a in (args[1:] if args[0].startswith("-") else args)]
    rc = 0
    for pid in pids:
        exists = (root() / str(pid)).exists()
        log_signal(f"kill {sig} {pid}{'' if exists else ' (no such process)'}")
        if exists:
            deliver(pid, sig)
        else:
            rc = 1
    return rc


def cmd_mk(args: List[str]) -> int:
    """mk <pid> <sid> <ppid> <start> <json: {"argv": [...], "env": {...}, ...behaviour}>"""
    pid, sid, ppid, start = (int(a) for a in args[:4])
    spec = json.loads(args[4])
    argv, env = spec.pop("argv"), spec.pop("env", {})
    make(pid, sid, ppid, start, argv, env, spec)
    return 0


def cmd_pad(args: List[str]) -> int:
    """pad <pid> <environ|cmdline> <n>: append n NUL-terminated filler entries of about 1 KiB, each holding a newline.

    The existing entries (the ownership token, the exit file) stay first, and the file grows past a pipe buffer (64 KiB)
    plus a reader's first read, so a reader that stops at the first match cannot have consumed it all by then.
    """
    pid, name, count = int(args[0]), args[1], int(args[2])
    assert name in ("environ", "cmdline"), f"fake pad supports environ and cmdline, got {name}"
    filler = b"".join(b"ROBOSIM_PAD_%05d=%s\n%s\0" % (i, b"x" * 500, b"y" * 500) for i in range(count))
    with open(root() / str(pid) / name, "ab") as f:
        f.write(filler)
    return 0


def spawn_recorder(me: int, argv: List[str]) -> int:
    """setsid stub for record_d0.sh: nohup bash -c SCRIPT PIDFILE EXITFILE [STAMPFILE] timeout -s INT MAX cmd..."""
    k = argv.index("-c")
    files = argv[k + 2:argv.index("timeout")]
    pidfile, exitfile = files[0], files[1]
    stampfile = files[2] if len(files) > 2 else None
    name = Path(exitfile).name[:-len(".exit")]
    env = dict(os.environ)
    wrapper_argv = argv[1:]  # after exec: bash -c SCRIPT files... timeout ...
    if name in os.environ.get("FAKE_DEAD", "").split(","):  # the recorder ended at once (status FAKE_DEAD_EXIT)
        Path(exitfile).write_text(os.environ.get("FAKE_DEAD_EXIT", "1") + "\n")
        if stampfile:
            Path(stampfile).write_text("0\n")  # its line stamper then ends normally at end of input
        Path(pidfile).write_text(f"{me}\n")
        return 0
    start = next_counter("start", 1000)
    rec = next_counter("pid", FIRST_FAKE_PID)
    rec_exit = int(os.environ.get(f"FAKE_EXIT_{name}", "2"))
    make(rec, me, me, start + 1, argv[argv.index("timeout"):], env,
         {"dies_on": ["INT", "TERM"], "exit_on": {"INT": rec_exit}})
    follows, on_exit = [rec], [[exitfile, f"{{status:{rec}}}"]]
    if stampfile:
        stamp = next_counter("pid", FIRST_FAKE_PID)
        make(stamp, me, me, start + 1, ["python3", "-u", "-c", "stamp"], env,
             {"follows": [rec], "status": int(os.environ.get("FAKE_STAMP_RC", "0"))})
        follows.append(stamp)
        on_exit.append([stampfile, f"{{status:{stamp}}}"])
    make(me, me, 1, start, wrapper_argv, env, {"follows": follows, "on_exit": on_exit}, comm="bash")
    if name not in os.environ.get("FAKE_NOPID", "").split(","):
        Path(pidfile).write_text(f"{me}\n")
    return 0


def spawn_nav2(me: int, argv: List[str]) -> int:
    """setsid stub for start_nav2.sh: nohup env ... bash -c SCRIPT PIDFILE EXITFILE [launch args...]"""
    k = argv.index("-c")
    pidfile, exitfile = argv[k + 2], argv[k + 3]
    env = dict(os.environ)
    start = next_counter("start", 1000)
    launch = next_counter("pid", FIRST_FAKE_PID)
    make(launch, me, me, start + 1, ["/usr/bin/python3", "/opt/ros/jazzy/bin/ros2", "launch", "carter_navigation",
                                     "carter_navigation.launch.xml", *argv[k + 4:]], env,
         {"dies_on": ["INT", "TERM"], "exit_on": {"INT": 1}})
    make(me, me, 1, start, argv[argv.index("bash"):], env,
         {"follows": [launch], "on_exit": [[exitfile, f"{{status:{launch}}}"]]}, comm="bash")
    Path(pidfile).write_text(f"{me}\n")
    return 0


def main(argv: List[str]) -> int:
    cmd, args = argv[0], argv[1:]
    if cmd == "pgrep":
        return cmd_pgrep(args)
    if cmd == "pkill":
        return cmd_pkill(args)
    if cmd == "kill":
        return cmd_kill(args)
    if cmd == "mk":
        return cmd_mk(args)
    if cmd == "pad":
        return cmd_pad(args)
    if cmd == "spawn":
        me, rest = int(args[0]), args[1:]
        mode = os.environ.get("FAKE_SPAWN", "")
        with open(root().parent / "calls.log", "a", encoding="utf-8") as f:
            f.write("setsid " + " ".join(rest) + "\n")
        if mode == "recorder":
            return spawn_recorder(me, rest)
        if mode == "nav2":
            return spawn_nav2(me, rest)
        if mode == "exec":
            os.execvp(rest[0], rest)
        print(f"fakeproc: FAKE_SPAWN={mode!r} not supported", file=sys.stderr)
        return 99
    print(f"fakeproc: unknown command {cmd}", file=sys.stderr)
    return 99


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
