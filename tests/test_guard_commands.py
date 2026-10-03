"""Fixed-input tests for .claude/hooks/guard_commands.py, the PreToolUse hook that refuses git push, wsl --shutdown
and killing Isaac Sim's kit.exe (no Windows needed: PID lookups use a fake process table)."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "guard_commands.py"
_SPEC = importlib.util.spec_from_file_location("guard_commands", _PATH)
guard = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(guard)

PROCESSES = {29036: "kit.exe", 1234: "python.exe", 58304: "powershell.exe"}


def fake_image(pid):
    return PROCESSES.get(pid)


def verdict(command, tool="Bash"):
    return guard.decide({"tool_name": tool, "tool_input": {"command": command}}, pid_image=fake_image)


def encoded(script):
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


PUSH = [
    "git push",
    "git push origin master",
    "git -C D:/RoboSim-Eval push",
    'git -C "D:/Robo Sim" push --tags',
    "git -c http.proxy=x push",
    "git --no-pager push",
    "cd /d/RoboSim-Eval && git push",
    "git status; git push",
    "echo ok\ngit push",
    "git \\\n  push origin master",
    "FOO=1 git push",
    "env GIT_TRACE=1 git push",
    "timeout 60 git push",
    "echo x | xargs git push",
    "git.exe push",
    '"C:/Program Files/Git/cmd/git.exe" push',
    'bash -lc "cd /mnt/d/RoboSim-Eval && git push"',
    "result=$(git push 2>&1)",
    'powershell -NoProfile -Command "git push origin master"',
    f"powershell -EncodedCommand {encoded('git push')}",
    "cmd /c git push",
    'cmd.exe /c "git push"',
    "wsl -d Ubuntu -- git push",
    'wsl -d Ubuntu -- bash -lc "cd /mnt/d/RoboSim-Eval && git push"',
]

PUSH_POWERSHELL = [
    "git push",
    '& "C:\\Program Files\\Git\\cmd\\git.exe" push',
    "if ($ok) { git push }",
    "Start-Process git -ArgumentList 'push','origin'",
    "Start-Process powershell -ArgumentList '-Command','git push'",
    "iex 'git push'",
    "Invoke-Expression -Command 'git push origin'",
    "Set-Location 'C:\\Users\\'; git push",
]

SHUTDOWN = [
    ("wsl --shutdown", "Bash"),
    ("wsl.exe --shutdown", "Bash"),
    ("/c/Windows/System32/wsl.exe --shutdown", "Bash"),
    ("C:\\Windows\\System32\\wsl.exe --shutdown", "PowerShell"),
    ("cmd /c wsl --shutdown", "Bash"),
    ('powershell -Command "wsl --shutdown"', "Bash"),
    ("wsl --shutdown", "PowerShell"),
]

KIT = [
    ("taskkill /F /IM kit.exe", "Bash"),
    ("taskkill //F //IM kit.exe", "Bash"),
    ('taskkill.exe /FI "IMAGENAME eq kit.exe"', "PowerShell"),
    ("Stop-Process -Name kit -Force", "PowerShell"),
    ('Stop-Process -Name "kit"', "PowerShell"),
    ("Get-Process -Name kit | Stop-Process -Force", "PowerShell"),
    ("Get-Process kit | ForEach-Object { $_.Kill() }", "PowerShell"),
    ("(Get-Process kit).Kill()", "PowerShell"),
    ("spps -n kit", "PowerShell"),
    ("kill -Name kit", "PowerShell"),
    ("wmic process where \"name='kit.exe'\" delete", "Bash"),
    ('wmic process where name="kit.exe" call terminate', "PowerShell"),
    ("Get-CimInstance Win32_Process -Filter \"Name='kit.exe'\" | Invoke-CimMethod -MethodName Terminate", "PowerShell"),
    ("taskkill /PID 29036 /F", "PowerShell"),
    ("taskkill //F //PID 29036", "Bash"),
    ("Stop-Process -Id 29036", "PowerShell"),
    ("Stop-Process -Id 1234,29036 -Force", "PowerShell"),
    ("Stop-Process 29036", "PowerShell"),
    ("kill 29036", "PowerShell"),
    ("[System.Diagnostics.Process]::GetProcessById(29036).Kill()", "PowerShell"),
    ("wmic process where processid=29036 delete", "Bash"),
    ("wsl -d Ubuntu -- taskkill.exe /IM kit.exe", "Bash"),
    ('powershell -NoProfile -Command "Stop-Process -Name kit"', "Bash"),
]

ALLOWED = [
    ("git status", "Bash"),
    ("git log --oneline -5", "Bash"),
    ('git commit -m "docs: agents never git push"', "Bash"),
    ('git log --grep "push"', "Bash"),
    ('git stash push -m "wip"', "Bash"),
    ("git -C D:/RoboSim-Eval status", "PowerShell"),
    ("echo git push", "Bash"),
    ('grep -n "git push" AGENTS.md', "Bash"),
    ("rg 'wsl --shutdown' docs", "Bash"),
    ("Write-Output 'wsl --shutdown'", "PowerShell"),
    ("python -c \"print('git push')\"", "Bash"),
    ("cat <<'EOF' > notes.md\ngit push\nwsl --shutdown\nEOF", "Bash"),
    ("$text = @'\ngit push\n'@\nSet-Content notes.md $text", "PowerShell"),
    ("wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/verify.sh", "PowerShell"),
    ("wsl -l -v", "PowerShell"),
    ("wsl --status", "Bash"),
    ("Get-Process kit", "PowerShell"),
    ("Get-Process -Name kit | Select-Object Id, StartTime", "PowerShell"),
    ('echo "taskkill /IM kit.exe"', "Bash"),
    ("taskkill /PID 1234", "PowerShell"),
    ("Stop-Process -Id 58304", "PowerShell"),
    ("Stop-Process -Id 4321", "PowerShell"),
    ("kill 29036", "Bash"),
    ("pkill -INT -s 4242", "Bash"),
    ("cat toolkit.log | grep kill", "Bash"),
    ("tail -n 5 kit.log", "Bash"),
]


@pytest.mark.parametrize("command", PUSH)
def test_git_push_is_blocked_in_bash(command):
    assert verdict(command, "Bash").startswith(guard.REASON_PUSH)


@pytest.mark.parametrize("command", PUSH_POWERSHELL)
def test_git_push_is_blocked_in_powershell(command):
    assert verdict(command, "PowerShell").startswith(guard.REASON_PUSH)


@pytest.mark.parametrize("command,tool", SHUTDOWN)
def test_wsl_shutdown_is_blocked(command, tool):
    assert verdict(command, tool).startswith(guard.REASON_SHUTDOWN)


@pytest.mark.parametrize("command,tool", KIT)
def test_killing_kit_is_blocked(command, tool):
    assert verdict(command, tool).startswith(guard.REASON_KIT)


@pytest.mark.parametrize("command,tool", ALLOWED)
def test_ordinary_commands_pass(command, tool):
    assert verdict(command, tool) is None


def test_other_tools_and_missing_commands_pass():
    assert guard.decide({"tool_name": "Write", "tool_input": {"content": "git push"}}, pid_image=fake_image) is None
    assert guard.decide({"tool_name": "Bash", "tool_input": {}}, pid_image=fake_image) is None
    assert guard.decide({}, pid_image=fake_image) is None


def test_a_failed_pid_lookup_lets_the_command_run():
    payload = {"tool_name": "PowerShell", "tool_input": {"command": "Stop-Process -Id 29036"}}
    assert guard.decide(payload, pid_image=lambda pid: None) is None


def run_main(monkeypatch, capsys, raw):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw.encode("utf-8")), encoding="utf-8"))
    rc = guard.main()
    return rc, capsys.readouterr().err


def test_main_blocks_with_exit_2_and_the_reason_on_stderr(monkeypatch, capsys):
    payload = {"tool_name": "Bash", "tool_input": {"command": "cd /d/RoboSim-Eval && git push"}}
    rc, err = run_main(monkeypatch, capsys, json.dumps(payload))
    assert rc == 2 and "Blocked by .claude/hooks/guard_commands.py" in err and "git push" in err


def test_main_allows_with_exit_0_and_keeps_non_ascii_commands(monkeypatch, capsys):
    payload = {"tool_name": "Bash", "tool_input": {"command": 'git commit -m "docs: 整理文档,不 push"'}}
    assert run_main(monkeypatch, capsys, json.dumps(payload, ensure_ascii=False)) == (0, "")


def test_main_reports_a_bad_payload_without_blocking(monkeypatch, capsys):
    rc, err = run_main(monkeypatch, capsys, "not json")
    assert rc == 1 and "not JSON" in err
