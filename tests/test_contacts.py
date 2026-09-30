"""Fixed-input tests for the WSL-side contact client (robosim_eval/contacts.py).

The Windows client is replaced by a stub executable in a temp directory that prints fixed bytes, so the tests need no
Windows interop, no Isaac and no network. The byte strings reproduce what powershell.exe writes on this zh-CN machine
(console code page 936): localized error text in GBK on stderr, and optionally UTF-16 output.
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from robosim_eval import contacts
from robosim_eval.contacts import ContactError

# isaac_py.ps1's uncaught-exception text as the verifier captured it (GBK on stderr, exit 1)
GBK_ERROR = "使用“1”个参数调用“ReadAllText”时发生异常:“未能找到路径的一部分。”".encode("gbk")


def _stub(tmp_path: Path, monkeypatch, stdout: bytes = b"", stderr: bytes = b"", rc: int = 0,
          sleep_s: float = 0.0) -> Path:
    """Point contacts at a stub 'powershell.exe' that writes fixed bytes; returns the file the stub logs argv to."""
    (tmp_path / "out.bin").write_bytes(stdout)
    (tmp_path / "err.bin").write_bytes(stderr)
    argv_log = tmp_path / "argv.txt"
    stub = tmp_path / "powershell.exe"
    stub.write_text("#!/bin/sh\n"
                    f"printf '%s\n' \"$@\" > '{argv_log}'\n"
                    + (f"sleep {sleep_s}\n" if sleep_s else "")
                    + f"cat '{tmp_path / 'out.bin'}'\n"
                    f"cat '{tmp_path / 'err.bin'}' >&2\n"
                    f"exit {rc}\n", encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setattr(contacts, "POWERSHELL", str(stub))
    return argv_log


def _envelope(result: Any) -> bytes:
    """python_server reply as isaac_py.ps1 prints it (one JSON line, CRLF)."""
    return (json.dumps({"status": "ok", "output": "", "result": json.dumps(result)}) + "\r\n").encode("ascii")


INSTALLED: Dict[str, Any] = {"ok": True, "bodies": ["/World/Nova_Carter_ROS/chassis_link"], "subscribed": True}


# ---- simctl-1: any failure of the contact channel is a ContactError --------------------------------------------------

def test_localized_stderr_without_json_is_a_contact_error(tmp_path, monkeypatch):
    # e.g. Invoke-Kit's ReadToEnd hits ReceiveTimeout: uncaught .NET exception, exit 1, GBK text on stderr only
    _stub(tmp_path, monkeypatch, stderr=GBK_ERROR, rc=1)
    for fn in (contacts.install, contacts.fetch):
        with pytest.raises(ContactError) as exc:
            fn()
        assert "exit 1" in str(exc.value) and "ReadAllText" in str(exc.value)


def test_gbk_json_error_line_is_decoded(tmp_path, monkeypatch):
    # ConvertTo-Json output of a localized .NET message, written in the console code page
    line = json.dumps({"status": "error", "evalue": "由于目标计算机积极拒绝,无法连接。"}, ensure_ascii=False)
    _stub(tmp_path, monkeypatch, stdout=(line + "\r\n").encode("gbk"), rc=3)
    with pytest.raises(ContactError) as exc:
        contacts.install()
    assert "无法连接" in str(exc.value)


def test_utf16_output_is_decoded(tmp_path, monkeypatch):
    out = ("﻿" + json.dumps({"status": "ok", "result": json.dumps(INSTALLED)}) + "\r\n").encode("utf-16-le")
    _stub(tmp_path, monkeypatch, stdout=out)
    assert contacts.install()["bodies"] == INSTALLED["bodies"]


def test_ok_reply_with_localized_warning_on_stderr_still_returns(tmp_path, monkeypatch):
    _stub(tmp_path, monkeypatch, stdout=_envelope(INSTALLED), stderr="警告: 测试".encode("gbk"))
    assert contacts.install()["ok"] is True


def test_undecodable_bytes_never_escape(tmp_path, monkeypatch):
    # neither valid UTF-8 nor valid GBK
    _stub(tmp_path, monkeypatch, stdout=b"\xff\x80\xff\r\n", stderr=b"\x81\xff\x00\xfe", rc=1)
    with pytest.raises(ContactError):
        contacts.fetch()


@pytest.mark.parametrize("line", [b"[1, 2]", b"42", b"null", b'"ok"'])
def test_reply_that_is_not_an_object_is_a_contact_error(tmp_path, monkeypatch, line):
    _stub(tmp_path, monkeypatch, stdout=line + b"\r\n")
    with pytest.raises(ContactError):
        contacts.install()


@pytest.mark.parametrize("result", [[1], None, "text", 3])
def test_monitor_result_that_is_not_an_object_is_a_contact_error(tmp_path, monkeypatch, result):
    _stub(tmp_path, monkeypatch, stdout=_envelope(result))
    for fn in (contacts.install, contacts.fetch):
        with pytest.raises(ContactError):
            fn()


def test_python_server_error_is_a_contact_error(tmp_path, monkeypatch):
    line = json.dumps({"status": "error", "ename": "NameError", "evalue": "name 'x' is not defined"})
    _stub(tmp_path, monkeypatch, stdout=(line + "\r\n").encode("ascii"), rc=1)
    with pytest.raises(ContactError, match="NameError"):
        contacts.fetch()


def test_client_that_does_not_start_is_a_contact_error(tmp_path, monkeypatch):
    monkeypatch.setattr(contacts, "POWERSHELL", str(tmp_path / "missing.exe"))
    with pytest.raises(ContactError, match="did not run"):
        contacts.install()


def test_client_that_hangs_is_a_contact_error(tmp_path, monkeypatch):
    _stub(tmp_path, monkeypatch, stdout=_envelope(INSTALLED), sleep_s=5)
    with pytest.raises(ContactError, match="did not run"):
        contacts._call("robosim_contacts_install()", timeout=0.5)


# ---- simctl-2 / contract C4: completeness signals reach the caller ---------------------------------------------------

ROBOT = "/World/Nova_Carter_ROS"
GROUND = "/World/warehouse_with_forklifts/GroundPlane/collisionPlane"
BOX = "/World/RoboSimObstacles/low_box"


def _kit_fetch(events=(), persist=None, dropped=0) -> Dict[str, Any]:
    """robosim_contacts_fetch() output (shape of artifacts/d3/contact-fetch-after-reset.json)."""
    return {"ok": True, "events": list(events), "persist_counts": dict(persist or {}), "dropped": dropped,
            "bodies": [f"{ROBOT}/chassis_link", f"{ROBOT}/wheel_left"], "subscribed": True, "timeline_time": 1.08}


def _event(kind: str, a0: str, a1: str) -> Dict[str, Any]:
    return {"type": kind, "actor0": a0, "actor1": a1, "collider0": a0, "collider1": a1}


def test_fetch_returns_persist_pairs_and_dropped(tmp_path, monkeypatch):
    persist = {f"{ROBOT}/wheel_left|{GROUND}": 132, f"{ROBOT}/wheel_left|{BOX}": 40}
    _stub(tmp_path, monkeypatch, stdout=_envelope(_kit_fetch(persist=persist, dropped=7)))
    got = contacts.fetch()
    assert got["dropped"] == 7
    assert sorted(got["persist_pairs"]) == sorted([[f"{ROBOT}/wheel_left", GROUND], [f"{ROBOT}/wheel_left", BOX]])
    assert got["events"] == []


def test_persist_only_contact_is_a_found_pair(tmp_path, monkeypatch):
    # an obstacle already touching the robot at the pre-run clear: its FOUND was cleared, only PERSIST remains
    persist = {f"{ROBOT}/wheel_left|{GROUND}": 3000, f"{ROBOT}/wheel_left|{BOX}": 2900}
    _stub(tmp_path, monkeypatch, stdout=_envelope(_kit_fetch(persist=persist)))
    pairs = contacts.found_pairs(contacts.fetch())
    assert (f"{ROBOT}/wheel_left", BOX) in pairs
    assert (f"{ROBOT}/wheel_left", GROUND) in pairs  # ground contacts are dropped later by the evaluator's policy


def test_found_pairs_keep_found_events_and_add_each_persist_pair_once():
    fetched = {"events": [_event("found", f"{ROBOT}/chassis_link", BOX), _event("lost", f"{ROBOT}/chassis_link", BOX),
                          _event("found", f"{ROBOT}/chassis_link", BOX)],
               "persist_pairs": [[BOX, f"{ROBOT}/chassis_link"], [f"{ROBOT}/wheel_left", BOX]], "dropped": 0}
    assert contacts.found_pairs(fetched) == [(f"{ROBOT}/chassis_link", BOX), (f"{ROBOT}/chassis_link", BOX),
                                             (f"{ROBOT}/wheel_left", BOX)]


@pytest.mark.parametrize("broken", [
    {"dropped": None}, {"dropped": "0"}, {"dropped": -1}, {"dropped": True}, {"dropped": 1.5},
    {"events": None}, {"events": {"type": "found"}}, {"events": [{"type": "found", "actor0": ROBOT}]},
    {"events": ["found"]}, {"persist_counts": None}, {"persist_counts": {"no-separator": 3}},
    {"persist_counts": {f"{ROBOT}|": 3}},
])
def test_fetch_with_missing_or_malformed_completeness_data_is_a_contact_error(tmp_path, monkeypatch, broken):
    # without these the caller could not tell "no contact" from "not measured"; unknown must not become pass
    out = {**_kit_fetch(), **broken}
    _stub(tmp_path, monkeypatch, stdout=_envelope(out))
    with pytest.raises(ContactError):
        contacts.fetch()


@pytest.mark.parametrize("key", ["dropped", "events", "persist_counts"])
def test_fetch_without_a_completeness_field_is_a_contact_error(tmp_path, monkeypatch, key):
    out = _kit_fetch()
    del out[key]
    _stub(tmp_path, monkeypatch, stdout=_envelope(out))
    with pytest.raises(ContactError):
        contacts.fetch()


# ---- the Windows side: scripts/windows/isaac_py.ps1 through WSL interop ----------------------------------------------
# Each case is its own powershell.exe that dot-sources the client (functions only), points it at a fake token file and
# at a private listener on an ephemeral 127.0.0.1 port, and then runs the client's main flow. The harness exits 99
# before the main flow if the port were ever python_server's 8226, so nothing can reach the live Isaac.

REPO = Path(__file__).resolve().parents[1]
FAKE_TOKEN = "robosim-test-token-7f3a"
windows_only = pytest.mark.skipif(not (Path(contacts.POWERSHELL).exists() and str(REPO).startswith("/mnt/")),
                                  reason="needs Windows PowerShell through WSL interop and the checkout on a Windows drive")

# python_server stand-in, run in a second runspace: one reply mode per accepted connection
FAKE_SERVER = r"""
param($Listener, $Modes, $Token)
foreach ($mode in $Modes) {
    $c = $Listener.AcceptTcpClient()
    $s = $c.GetStream()
    $ms = New-Object System.IO.MemoryStream
    $buf = New-Object byte[] 65536
    while (($n = $s.Read($buf, 0, $buf.Length)) -gt 0) { $ms.Write($buf, 0, $n) }
    $req = [System.Text.Encoding]::UTF8.GetString($ms.ToArray()) | ConvertFrom-Json
    if ($mode -eq 'reset') {  # RST: close the socket itself with linger 0 (TcpClient.Close would send a FIN first)
        $c.Client.LingerState = New-Object System.Net.Sockets.LingerOption($true, 0); $c.Client.Close(); continue
    }
    if ($mode -eq 'silent') { Start-Sleep -Seconds 5; $c.Close(); continue }
    if ($mode -eq 'empty') { $c.Close(); continue }
    $reply = '<html>not json'
    if ($mode -eq 'ok') {
        if ($req.auth_token -eq $Token -and $req.context -eq 'robosim' -and $req.code) {
            $reply = '{"status": "ok", "output": "", "result": "{\"ok\": true}"}'
        } else {
            $reply = '{"status": "error", "ename": "AuthError", "evalue": "unexpected envelope"}'
        }
    }
    $b = [System.Text.Encoding]::UTF8.GetBytes($reply)
    $s.Write($b, 0, $b.Length)
    $c.Close()
}
"""

CLOSED_PORT = """
$l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
$l.Start(); $Port = $l.LocalEndpoint.Port; $l.Stop()
"""

SERVER_PORT = """
$srv = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
$srv.Start(); $Port = $srv.LocalEndpoint.Port
$rs = [PowerShell]::Create().AddScript(@'
__SERVER__
'@).AddArgument($srv).AddArgument(@(__MODES__)).AddArgument('__TOKEN__')
$null = $rs.BeginInvoke()
"""


def _winpath(path: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=True).stdout.strip()


def _ps_script(args: str, setup: str, code_file: str = "", run: str = "Invoke-IsaacPy") -> str:
    """Dot-source the client with `args`, set $Port in `setup`, then assign $CodeFile (a PowerShell expression that may
    use $kit, the client's allowed root) and run `run`."""
    client = _winpath(REPO / "scripts" / "windows" / "isaac_py.ps1")
    return (f"$ErrorActionPreference = 'Stop'\n"
            f". '{client}' {args}\n"
            f"$kit = Get-AllowedKitRoot\n"
            f"{setup}\n"
            f"if ($Port -eq 8226) {{ exit 99 }}\n"
            + (f"$CodeFile = {code_file}\n" if code_file else "")
            + f"{run}\n")


def _run_ps(scripts: Dict[str, Any]) -> Dict[str, Tuple[int, bytes, bytes]]:
    """Run the PowerShell scripts (text, or a list of -File arguments) in parallel; name -> (exit code, stdout bytes,
    stderr bytes)."""
    procs = {}
    for name, script in scripts.items():
        if isinstance(script, list):
            cmd = ["-File"] + script
        else:
            cmd = ["-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii")]
        procs[name] = subprocess.Popen([contacts.POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                                        "Bypass"] + cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = {}
    for name, p in procs.items():
        stdout, stderr = p.communicate(timeout=60)
        out[name] = (p.returncode, stdout, stderr)
    return out


# -CodeFile values as PowerShell expressions ($kit = the client's allowed root, with a trailing backslash); all exit 2
PATH_CASES = {
    "kit_dir_itself": '"$kit"',
    "bracket_wildcard": '"${kit}contact_monito[r].py"',
    "star_wildcard": '"${kit}*.py"',
    "ads_stream": '"${kit}contact_monitor.py::`$DATA"',
    "missing_file": '"${kit}no_such_file.py"',
    "parent_escape": '"${kit}..\\contacts.py"',
    "empty": "''",
    "non_ascii_name": '"${kit}中文.py"',
}
TRANSPORT_CASES = {  # fake server modes per connection, -Call given?, expected exit code
    "ok_file_only": ("'ok'", False, 0),
    "ok_with_call": ("'ok','ok'", True, 0),
    "refused": (None, True, 3),
    "reset_on_file": ("'reset'", True, 3),
    "reset_on_call": ("'ok','reset'", True, 3),
    "garbage_reply": ("'garbage'", False, 5),
    "garbage_on_call": ("'ok','garbage'", True, 5),
    "empty_reply": ("'empty'", True, 5),
}


@pytest.fixture(scope="module")
def ps_results(tmp_path_factory) -> Dict[str, Tuple[int, bytes, bytes]]:
    token_log = tmp_path_factory.mktemp("isaac_py") / "isaac-console.log"
    token_log.write_text(f"[Info] Python server authentication token: {FAKE_TOKEN}\n", encoding="utf-8")
    args = f"-CodeFile 'unset' -ConsoleLog '{_winpath(token_log)}'"

    def server(modes: str) -> str:
        return SERVER_PORT.replace("__SERVER__", FAKE_SERVER).replace("__MODES__", modes).replace("__TOKEN__", FAKE_TOKEN)

    scripts = {f"path:{name}": _ps_script(args, CLOSED_PORT, code_file) for name, code_file in PATH_CASES.items()}
    scripts["path:not_given"] = _ps_script(f"-ConsoleLog '{_winpath(token_log)}'", CLOSED_PORT)
    for name, (modes, with_call, _) in TRANSPORT_CASES.items():
        call = " -Call 'robosim_diag_bodies()'" if with_call else ""
        scripts[f"net:{name}"] = _ps_script(args + call, CLOSED_PORT if modes is None else server(modes),
                                            "$kit + 'diag_stage.py'")
    scripts["fn:receive_timeout"] = _ps_script(args, server("'silent'"), run=(
        "try { $r = Invoke-Kit 'x' 'token' $Port 'robosim' 1 1000; "
        "@{ threw = $false; error = [string]$r.error; reply = [string]$r.reply } | ConvertTo-Json -Compress } "
        "catch { @{ threw = $true; error = $_.Exception.GetType().Name } | ConvertTo-Json -Compress }"))
    scripts["fn:allowed_root"] = _ps_script(args, "$Port = 1", run="Write-Output (Get-AllowedKitRoot)")
    # any other failure inside the client (simulated by replacing one of its functions after dot-sourcing)
    scripts["fn:unexpected"] = _ps_script(args, CLOSED_PORT, "$kit + 'diag_stage.py'", run=(
        "function Read-ServerToken { throw 'simulated client failure' }\nInvoke-IsaacPy"))
    # run as a file, the way contacts._call starts it; both stop before any connection (port 9 is never used)
    client, kit = _winpath(REPO / "scripts" / "windows" / "isaac_py.ps1"), _winpath(REPO / "robosim_eval" / "kit")
    missing_log = _winpath(token_log.parent / "no-such-console.log")
    scripts["file:missing_code_file"] = [client, "-CodeFile", kit + "\\no_such_file.py", "-ConsoleLog", missing_log,
                                         "-Port", "9"]
    scripts["file:no_token"] = [client, "-CodeFile", kit + "\\diag_stage.py", "-ConsoleLog", missing_log, "-Port", "9"]
    return _run_ps(scripts)


def _json_status_line(stdout: bytes) -> Dict[str, Any]:
    lines = [ln for ln in contacts._decode(stdout).splitlines() if ln.strip()]
    assert lines, "no output on stdout"
    obj = json.loads(lines[-1])
    assert isinstance(obj, dict) and obj.get("status") in ("ok", "error"), obj
    return obj


@windows_only
@pytest.mark.parametrize("name", sorted(PATH_CASES) + ["not_given"])
def test_client_rejects_bad_code_files_with_exit_2_and_a_json_line(ps_results, name):
    # the documented "2 bad arguments" with a JSON status line, never an uncaught .NET error (exit 1, stderr only)
    rc, stdout, stderr = ps_results[f"path:{name}"]
    assert rc == 2, (rc, contacts._decode(stdout), contacts._decode(stderr)[-600:])
    assert _json_status_line(stdout)["status"] == "error"
    assert stdout.isascii()  # no console code page can garble it


@windows_only
def test_client_escapes_non_ascii_text_in_its_json(ps_results):
    rc, stdout, _ = ps_results["path:non_ascii_name"]
    assert stdout.isascii() and "中文.py" in _json_status_line(stdout)["evalue"]


@windows_only
@pytest.mark.parametrize("name", sorted(TRANSPORT_CASES))
def test_client_turns_transport_failures_into_a_json_line_and_exit_code(ps_results, name):
    rc, stdout, stderr = ps_results[f"net:{name}"]
    expected = TRANSPORT_CASES[name][2]
    assert rc == expected, (rc, contacts._decode(stdout), contacts._decode(stderr)[-600:])
    assert _json_status_line(stdout)["status"] == ("ok" if expected == 0 else "error")
    assert stdout.isascii()


@windows_only
def test_client_receive_timeout_is_returned_not_thrown(ps_results):
    rc, stdout, stderr = ps_results["fn:receive_timeout"]
    out = json.loads(contacts._decode(stdout).strip().splitlines()[-1])
    assert out["threw"] is False and out["error"] and not out["reply"], (out, contacts._decode(stderr)[-600:])


@windows_only
def test_client_accepts_only_its_own_checkouts_kit_dir(ps_results):
    rc, stdout, _ = ps_results["fn:allowed_root"]
    assert rc == 0
    assert contacts._decode(stdout).strip() == _winpath(REPO / "robosim_eval" / "kit") + "\\"


@windows_only
def test_client_reports_an_unexpected_failure_as_json(ps_results):
    rc, stdout, stderr = ps_results["fn:unexpected"]
    assert rc == 6, (rc, contacts._decode(stdout), contacts._decode(stderr)[-600:])
    assert "simulated client failure" in _json_status_line(stdout)["evalue"] and stdout.isascii()


@windows_only
@pytest.mark.parametrize("name, expected", [("missing_code_file", 2), ("no_token", 4)])
def test_client_run_as_a_file_still_runs_its_main_flow(ps_results, name, expected):
    rc, stdout, stderr = ps_results[f"file:{name}"]
    assert rc == expected, (rc, contacts._decode(stdout), contacts._decode(stderr)[-600:])
    assert _json_status_line(stdout)["status"] == "error" and stdout.isascii()


# ---- contract C6: the client and the Kit file come from the checkout contacts.py is in ---------------------------------

@pytest.mark.parametrize("wsl, win", [
    ("/mnt/d/RoboSim-Eval/scripts/windows/isaac_py.ps1", r"D:\RoboSim-Eval\scripts\windows\isaac_py.ps1"),
    ("/mnt/c/Users/A B/wt/robosim_eval/kit/contact_monitor.py", r"C:\Users\A B\wt\robosim_eval\kit\contact_monitor.py"),
    ("/mnt/c", "C:\\"),
    ("/home/user/RoboSim-Eval/x.py", None),
    ("/mnt/wsl/x.py", None),
    ("/mnt", None),
])
def test_windows_path_of_a_wsl_path(wsl, win):
    assert contacts.windows_path(Path(wsl)) == win


@windows_only
def test_client_and_kit_file_are_the_ones_of_this_checkout(tmp_path, monkeypatch):
    argv_log = _stub(tmp_path, monkeypatch, stdout=_envelope(INSTALLED))
    contacts.install()
    argv = argv_log.read_text(encoding="utf-8").splitlines()
    assert argv[argv.index("-File") + 1] == _winpath(REPO / "scripts" / "windows" / "isaac_py.ps1")
    assert argv[argv.index("-CodeFile") + 1] == _winpath(REPO / "robosim_eval" / "kit" / "contact_monitor.py")
    assert argv[argv.index("-Call") + 1] == "robosim_contacts_install()"


def test_checkout_outside_a_windows_drive_is_a_contact_error(tmp_path, monkeypatch):
    _stub(tmp_path, monkeypatch, stdout=_envelope(INSTALLED))
    monkeypatch.setattr(contacts, "CLIENT", None)
    with pytest.raises(ContactError, match="Windows drive"):
        contacts.install()
