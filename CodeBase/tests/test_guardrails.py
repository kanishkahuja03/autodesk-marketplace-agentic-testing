"""Tests for the tool-call guardrails (ARCHITECTURE.md D32, D33). Run with: uv run pytest"""

import json
from types import SimpleNamespace

import pytest

from mpagent.execute.guardrails import check_tool_call, tool_guardrail
from mpagent.runlog import Trace

GUID = "{DFA9AB30-EDDB-4E96-BFF7-086145A9E483}"


@pytest.fixture
def run_dir(tmp_path):
    return tmp_path / "runs" / "app" / "20261012-120000"


def ps(command, run_dir):
    return check_tool_call("PowerShell", {"command": command}, run_dir)


@pytest.mark.parametrize("command", [
    ("Start-Process -FilePath msiexec.exe -ArgumentList '/i','\"C:\\in\\x.msi\"','/qn','/norestart','/l*v',"
     "'\"C:\\runs\\evidence\\install.log\"' -Wait -PassThru | Select-Object -ExpandProperty ExitCode"),
    'Get-AuthenticodeSignature -FilePath "C:\\in\\x.msi" | Format-List Status, StatusMessage, SignerCertificate',
    f"Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GUID}'",
    "Get-ChildItem Env:APPDATA",
    "test-path 'C:\\Users\\x\\AppData\\Roaming\\Autodesk\\ApplicationPlugins\\pidExport.bundle'",
    "Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture",
    ("([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent())"
     ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"),
])
def test_allowed_powershell(command, run_dir):
    assert ps(command, run_dir) is None


@pytest.mark.parametrize("command, reason", [
    ("Remove-Item C:\\temp -Recurse", "must start with"),
    ("Invoke-WebRequest https://example.com", "must start with"),
    ("msiexec /x " + GUID + " /qn", "must start with"),                 # bare msiexec: no wait, no exit code
    ("Start-Process -FilePath powershell.exe -ArgumentList 'x'", "must start with"),
    ("Get-ChildItem C:\\ ; Remove-Item C:\\x", "';'"),                  # second command hidden after an allowed one
    ("Get-ChildItem C:\\ | ForEach-Object Delete", "pipe target"),
    ("Get-ChildItem | Where-Object { $_.Delete() }", "'{'"),           # script block
    ("Test-Path $(Remove-Item x)", "'$('"),
    ("Get-ChildItem C:\\ > C:\\out.txt", "'>'"),
    ("Get-ChildItem C:\\\nRemove-Item x", "line break"),
])
def test_rejected_powershell(command, reason, run_dir):
    result = ps(command, run_dir)
    assert result is not None and reason in result


@pytest.mark.parametrize("mode, allowed", [("get", True), ("list", True), ("set", False), ("delete", False)])
def test_registry_is_read_only(mode, allowed, run_dir):
    result = check_tool_call("Registry", {"mode": mode, "path": "HKCU:\\Software\\X"}, run_dir)
    assert (result is None) is allowed


def test_filesystem_rules(run_dir):
    inside = str(run_dir / "evidence" / "notes.txt")
    outside = "C:\\Windows\\temp.txt"
    fs = lambda **a: check_tool_call("FileSystem", a, run_dir)
    for mode in ("read", "list", "search", "info"):
        assert fs(mode=mode, path=outside) is None
    assert fs(mode="write", path=inside, content="x") is None
    assert "only allowed inside the run folder" in fs(mode="write", path=outside, content="x")
    assert "only allowed inside the run folder" in fs(mode="write", path="notes.txt", content="x")  # Desktop-relative
    assert fs(mode="copy", path=outside, destination=inside) is None
    assert fs(mode="copy", path=inside, destination=outside) is not None
    assert fs(mode="move", path=outside, destination=inside) is not None  # would remove the source
    assert "never allowed" in fs(mode="delete", path=inside)
    assert fs(mode="write", path=str(run_dir / ".." / ".." / "escape.txt"), content="x") is not None


def test_process_kill_only_for_msiexec(run_dir):
    assert check_tool_call("Process", {"mode": "list"}, run_dir) is None
    assert check_tool_call("Process", {"mode": "kill", "name": "msiexec.exe"}, run_dir) is None
    assert check_tool_call("Process", {"mode": "kill", "name": "devenv.exe"}, run_dir) is not None


def test_ui_tools_are_not_restricted(run_dir):
    assert check_tool_call("Click", {"label": 3}, run_dir) is None
    assert check_tool_call("App", {"mode": "launch_executable", "executable": "control.exe"}, run_dir) is None


def test_sdk_guardrail_rejects_logs_and_traces(run_dir):
    run_dir.mkdir(parents=True)
    guard = tool_guardrail(run_dir, Trace(run_dir))
    data = lambda tool, args: SimpleNamespace(context=SimpleNamespace(tool_name=tool, tool_arguments=json.dumps(args)))

    allowed = guard.guardrail_function(data("Registry", {"mode": "get", "path": "HKLM:\\X"}))
    rejected = guard.guardrail_function(data("Registry", {"mode": "delete", "path": "HKLM:\\X"}))

    assert allowed.behavior["type"] == "allow"
    assert rejected.behavior["type"] == "reject_content" and "read-only" in rejected.behavior["message"]
    assert "guardrail_reject" in (run_dir / "trace.jsonl").read_text(encoding="utf-8")
