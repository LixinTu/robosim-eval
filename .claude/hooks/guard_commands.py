"""guard_commands.py - RoboSim Eval: Claude Code PreToolUse hook that refuses three commands this project never runs.

  git push          agents never push; the user pushes himself
  wsl --shutdown    it also stops docker-desktop and changes the WSL IP
  killing kit.exe   Isaac Sim is closed by the user in its GUI, never killed by a tool

Configured in .claude/settings.json for the Bash and PowerShell tools. Reads the hook payload (JSON) on stdin and looks
only at tool_input.command. Exit 2 with the reason on stderr blocks the call (Claude Code passes the reason to the
model); exit 0 lets it run. A payload that is not JSON exits 1 (a non-blocking hook error) instead of blocking
every command.

A command is cut into simple commands at ; & | ( ) { } and line ends outside quotes, with the quoting and escape rules
of the shell that runs it (bash: backslash; PowerShell: backtick; cmd: caret); heredoc and here-string bodies are
skipped. Only the command word counts, found after variable assignments and wrappers such as sudo, env and timeout;
the inline scripts of bash -c, powershell -Command / -EncodedCommand, cmd /c, wsl [--|-e], Invoke-Expression and
Start-Process are checked the same way. So text that only mentions these commands (echo, grep, a commit message)
passes. Killing kit is recognised by name (kit, kit.exe) on the same line as a kill command, or by a PID that tasklist
reports as kit.exe (Windows only; a failed lookup lets the command run).
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Set, Tuple

PidImage = Callable[[int], Optional[str]]

REASON_PUSH = "git push is never run by agents in this project; the user pushes himself (AGENTS.md hard rules)."
REASON_SHUTDOWN = ("wsl --shutdown also stops docker-desktop and changes the WSL IP; it is not run without the "
                   "user's consent (AGENTS.md hard rules).")
REASON_KIT = "Isaac Sim (kit.exe) is never killed by a tool; the user closes it in its GUI (AGENTS.md hard rules)."

KIT_WORD = re.compile(r"(?<![\w.-])kit(?:\.exe)?(?![\w-])", re.IGNORECASE)
KILL_METHOD = re.compile(r"\.kill\s*\(", re.IGNORECASE)
GET_BY_ID_KILL = re.compile(r"getprocessbyid\s*\(\s*(\d+)\s*\)\s*\.\s*kill\s*\(", re.IGNORECASE)
WMIC_PID = re.compile(r"processid\s*=\s*['\"]?(\d+)", re.IGNORECASE)
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"(?<!<)<<-?(?!<)\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
SEPARATORS = set(";&|(){}")
MAX_DEPTH = 6

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
POWERSHELLS = {"powershell", "pwsh"}
KILL_WORDS = {"taskkill", "tskill", "stop-process", "spps", "kill", "pkill", "killall"}
# Wrappers that run the command after them, with the options that take a separate value.
WRAPPERS: Dict[str, Set[str]] = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
    "env": {"-u", "-C", "-S"},
    "nice": {"-n"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"},
    "stdbuf": {"-i", "-o", "-e"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "command": set(), "exec": set(), "nohup": set(), "time": set(), "builtin": set(), "call": set(),
}
PS_VALUE_PARAMS = {"-executionpolicy", "-ep", "-windowstyle", "-outputformat", "-inputformat", "-configurationname",
                   "-psconsolefile", "-version", "-workingdirectory", "-wd"}
WSL_VALUE_OPTIONS = {"-d", "--distribution", "-u", "--user", "--cd", "--shell-type", "--distribution-id"}
START_VALUE_PARAMS = {"-workingdirectory", "-windowstyle", "-redirectstandardoutput", "-redirectstandarderror",
                      "-redirectstandardinput", "-verb", "-credential"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}


def _word(token: str) -> str:
    """Command name of a token: base name, lower case, without .exe."""
    base = re.split(r"[\\/]", token)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _escapes(shell: str, in_double_quotes: bool, ch: str, nxt: str) -> bool:
    """Whether ch escapes the next character in this shell."""
    if shell == "PowerShell":
        return ch == "`"
    if shell == "cmd":
        return ch == "^" and not in_double_quotes
    if in_double_quotes:
        return ch == "\\" and nxt in "\"\\$`"
    return ch == "\\"


def _logical_lines(text: str, shell: str) -> List[str]:
    """Lines with continuations joined; heredoc (bash) and here-string (PowerShell) bodies left out."""
    cont = "`" if shell == "PowerShell" else "^" if shell == "cmd" else "\\"
    text = re.sub(re.escape(cont) + r"\r?\n", " ", text)
    lines: List[str] = []
    end: Optional[str] = None
    for line in text.splitlines():
        if end is not None:
            if line.strip() == end or (end in ("'@", '"@') and line.lstrip().startswith(end)):
                end = None
            continue
        lines.append(line)
        doc = HEREDOC.search(line) if shell == "Bash" else None
        if doc:
            end = doc.group(1)
        elif shell == "PowerShell" and line.rstrip().endswith(("@'", '@"')):
            end = line.rstrip()[-1] + "@"
    return lines


def _split(line: str, shell: str) -> List[str]:
    """Simple commands of one line: cut at unquoted ; & | ( ) { }."""
    parts: List[str] = []
    cur: List[str] = []
    quote: Optional[str] = None
    i = 0
    while i < len(line):
        ch, nxt = line[i], line[i + 1] if i + 1 < len(line) else ""
        if nxt and quote != "'" and _escapes(shell, quote == '"', ch, nxt):
            cur += [ch, nxt]
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in SEPARATORS:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p for p in parts if p.strip()]


def _tokens(segment: str, shell: str) -> List[str]:
    """Words of a simple command with quotes and escapes removed."""
    tokens: List[str] = []
    cur: List[str] = []
    quote: Optional[str] = None
    started = False
    i = 0
    while i < len(segment):
        ch, nxt = segment[i], segment[i + 1] if i + 1 < len(segment) else ""
        if nxt and quote != "'" and _escapes(shell, quote == '"', ch, nxt):
            cur.append(nxt)
            started = True
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
        elif ch in "\"'":
            quote, started = ch, True
        elif ch.isspace():
            if started:
                tokens.append("".join(cur))
            cur, started = [], False
        else:
            cur.append(ch)
            started = True
        i += 1
    if started:
        tokens.append("".join(cur))
    return tokens


def _skip_wrappers(tokens: List[str]) -> List[str]:
    """Drop variable assignments and wrappers (sudo, env, nohup, timeout, ...) in front of the command word."""
    i = 0
    while i < len(tokens):
        word = _word(tokens[i])
        if ASSIGNMENT.match(tokens[i]):
            i += 1
            continue
        if word not in WRAPPERS:
            break
        valued = WRAPPERS[word]
        i += 1
        while i < len(tokens) and (tokens[i].startswith("-") or (word == "env" and ASSIGNMENT.match(tokens[i]))):
            i += 2 if tokens[i] in valued else 1
        if word == "timeout":
            i += 1  # the duration
    return tokens[i:]


def _pids(tokens: List[str], flag_names: Tuple[str, ...], positional: bool) -> List[int]:
    """PIDs given after one of flag_names (comma lists allowed) or, if positional, as bare numbers."""
    pids: List[int] = []
    expect = False
    for tok in tokens:
        if expect:
            pids += [int(p) for p in tok.split(",") if p.strip().isdigit()]
            expect = False
        elif tok[:1] in ("/", "-") and tok.lower().lstrip("/-") in flag_names:
            expect = True
        elif positional and tok.isdigit():
            pids.append(int(tok))
    return pids


def _any_kit(pids: List[int], pid_image: Optional[PidImage]) -> bool:
    return pid_image is not None and any((pid_image(p) or "").lower() == "kit.exe" for p in pids)


def _cmd_line(tokens: List[str]) -> str:
    """cmd /c gets the rest of its command line verbatim: one token is that line, several are re-joined."""
    if len(tokens) == 1:
        return tokens[0]
    return " ".join(f'"{t}"' if any(c.isspace() for c in t) else t for t in tokens)


def _check_simple(tokens: List[str], shell: str, pid_image: Optional[PidImage],
                  depth: int) -> Tuple[Optional[str], bool]:
    """(block reason or None, whether this simple command is a kill command) for one argv."""
    tokens = _skip_wrappers(tokens)
    if not tokens or depth > MAX_DEPTH:
        return None, False
    word, args = _word(tokens[0]), tokens[1:]
    lower = [a.lower() for a in args]

    if word == "git":
        i = 0
        while i < len(args):
            if args[i] in GIT_VALUE_OPTIONS:
                i += 2
            elif args[i].startswith("-"):
                i += 1
            else:
                return (REASON_PUSH if lower[i] == "push" else None), False
        return None, False

    if word == "wsl":
        if "--shutdown" in lower:
            return REASON_SHUTDOWN, False
        i = 0
        while i < len(args):
            if lower[i] in ("--", "-e", "--exec"):
                return _check_simple(args[i + 1:], "Bash", pid_image, depth + 1)
            if lower[i] in WSL_VALUE_OPTIONS:
                i += 2
            elif args[i].startswith("-"):
                return None, False  # management options (-l, --status, -t, ...) run no command
            else:
                return _check_simple(args[i:], "Bash", pid_image, depth + 1)
        return None, False

    if word in SHELLS:
        for i, a in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", a) and i + 1 < len(args):
                return _check_text(args[i + 1], "Bash", pid_image, depth + 1), False
        return None, False

    if word in POWERSHELLS:
        i = 0
        while i < len(args):
            name = lower[i]
            if name in ("-command", "-c", "-com", "-comm", "-comma", "-comman"):
                return _check_text(" ".join(args[i + 1:]), "PowerShell", pid_image, depth + 1), False
            if name in ("-encodedcommand", "-enc", "-e", "-ec") and i + 1 < len(args):
                try:
                    script = base64.b64decode(args[i + 1]).decode("utf-16-le")
                except (ValueError, UnicodeDecodeError):
                    return None, False
                return _check_text(script, "PowerShell", pid_image, depth + 1), False
            if name in ("-file", "-f"):
                return None, False
            if name in PS_VALUE_PARAMS:
                i += 2
            elif args[i].startswith("-"):
                i += 1
            else:
                return _check_text(" ".join(args[i:]), "PowerShell", pid_image, depth + 1), False
        return None, False

    if word == "cmd":
        for i, a in enumerate(lower):
            if a in ("/c", "/k", "/r"):
                return _check_text(_cmd_line(args[i + 1:]), "cmd", pid_image, depth + 1), False
        return None, False

    if word in ("invoke-expression", "iex"):
        script = " ".join(a for a, low in zip(args, lower) if low not in ("-command", "-c"))
        return _check_text(script, "PowerShell", pid_image, depth + 1), False

    if word in ("start-process", "saps", "start"):
        kept: List[str] = []
        i = 0
        while i < len(args):
            if lower[i] in ("-argumentlist", "-args", "-a", "-filepath") and i + 1 < len(args):
                kept.append(args[i + 1].replace(",", " "))
                i += 2
            elif lower[i] in START_VALUE_PARAMS:
                i += 2
            elif args[i].startswith(("-", "/")):
                i += 1
            else:
                kept.append(args[i].replace(",", " "))
                i += 1
        return _check_text(" ".join(kept), "PowerShell", pid_image, depth + 1), False

    if word == "wmic":
        if not any(a in ("delete", "terminate") for a in lower):
            return None, False
        joined = " ".join(args)
        if KIT_WORD.search(joined) or _any_kit([int(p) for p in WMIC_PID.findall(joined)], pid_image):
            return REASON_KIT, True
        return None, True

    if word in ("invoke-cimmethod", "invoke-wmimethod"):
        return None, any("terminate" in a for a in lower)

    if word in KILL_WORDS:
        if any(KIT_WORD.search(a) for a in args):
            return REASON_KIT, True
        if word == "taskkill":
            pids = _pids(args, ("pid",), positional=False)
        elif word == "tskill":
            pids = _pids(args, (), positional=True)
        elif word in ("stop-process", "spps") or (word == "kill" and shell == "PowerShell"):
            pids = _pids(args, ("id",), positional=True)
        else:
            pids = []  # kill/pkill/killall from bash take MSYS or Linux PIDs, not Windows ones
        return (REASON_KIT if _any_kit(pids, pid_image) else None), True

    return None, False


def _check_text(text: str, shell: str, pid_image: Optional[PidImage], depth: int = 0) -> Optional[str]:
    """Block reason for a script run by this shell, or None."""
    if depth > MAX_DEPTH:
        return None
    for line in _logical_lines(text, shell):
        kill_on_line = False
        for segment in _split(line, shell):
            reason, is_kill = _check_simple(_tokens(segment, shell), shell, pid_image, depth)
            if reason:
                return f"{reason} (in: {segment.strip()[:200]})"
            kill_on_line = kill_on_line or is_kill
        if (kill_on_line or KILL_METHOD.search(line)) and KIT_WORD.search(line):
            return f"{REASON_KIT} (in: {line.strip()[:200]})"
        by_id = GET_BY_ID_KILL.search(line)
        if by_id and _any_kit([int(by_id.group(1))], pid_image):
            return f"{REASON_KIT} (in: {line.strip()[:200]})"
    return None


def tasklist_image(pid: int) -> Optional[str]:
    """Image name of a running Windows process (None when not on Windows, not running, or the lookup fails)."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    first = out.strip().splitlines()[0] if out.strip() else ""
    return first.split('","')[0].strip('"') if first.startswith('"') else None


def decide(payload: dict, pid_image: Optional[PidImage] = tasklist_image) -> Optional[str]:
    """Reason to block this tool call, or None to let it run."""
    tool = payload.get("tool_name", "")
    if tool not in ("Bash", "PowerShell"):
        return None
    command = (payload.get("tool_input") or {}).get("command") or ""
    return _check_text(str(command), tool, pid_image)


def main() -> int:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"guard_commands.py: the hook payload is not JSON ({exc}); command not checked", file=sys.stderr)
        return 1
    reason = decide(payload if isinstance(payload, dict) else {})
    if reason:
        print(f"Blocked by .claude/hooks/guard_commands.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
