"""Fixed-input tests for the WSL-side contact client (robosim_eval/contacts.py).

The Windows client is replaced by a stub executable in a temp directory that prints fixed bytes, so the tests need no
Windows interop, no Isaac and no network. The byte strings reproduce what powershell.exe writes on this zh-CN machine
(console code page 936): localized error text in GBK on stderr, and optionally UTF-16 output.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

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
