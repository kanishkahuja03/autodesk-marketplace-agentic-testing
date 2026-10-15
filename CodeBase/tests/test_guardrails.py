"""Tests for the tool-call guardrails (ARCHITECTURE.md D32, D33). Run with: uv run pytest"""

import json
from types import SimpleNamespace

import pytest

from mpagent.execute.guardrails import CallPolicy, check_tool_call, tool_guardrail
from mpagent.execute.host import HostLaunch
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
    ('Select-String -Path "C:\\runs\\evidence\\install.log" -Pattern "success or error status", '
     '"MainEngineThread is returning"'),
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


def test_ampersand_is_text_inside_quotes_but_rejected_outside(run_dir):
    # run 20261013-145150: every command naming 'P&ID Connector Exporter Plant3D' was rejected
    root = r"HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
    assert ps(f"Get-ChildItem '{root}' | Select-Object Name", run_dir) is None
    assert ps('Select-String -Path "C:\\run\\evidence\\install.log" -Pattern "P&ID Connector"', run_dir) is None
    assert "outside quotes" in ps("Get-ChildItem C:\\ & Remove-Item C:\\x", run_dir)
    assert "outside quotes" in ps("Test-Path 'C:\\a' && Remove-Item C:\\x", run_dir)
    assert "outside quotes" in ps("& 'C:\\evil.exe'", run_dir)


@pytest.mark.parametrize("mode, allowed", [("get", True), ("list", True), ("set", False), ("delete", False)])
def test_registry_is_read_only(mode, allowed, run_dir):
    result = check_tool_call("Registry", {"mode": mode, "path": "HKCU:\\Software\\X"}, run_dir)
    assert (result is None) is allowed


def test_filesystem_is_read_only(run_dir):
    # run 20261013-145150: Agent 2 overwrote the real evidence\install.log with its own sentence
    inside = str(run_dir / "evidence" / "install.log")
    outside = "C:\\Windows\\temp.txt"
    fs = lambda **a: check_tool_call("FileSystem", a, run_dir)
    for mode in ("read", "list", "search", "info"):
        assert fs(mode=mode, path=outside) is None
    for mode in ("write", "copy", "move", "delete"):
        reason = fs(mode=mode, path=inside, destination=inside, content="x")
        assert reason is not None and "read-only" in reason


def test_whole_file_read_of_large_file_is_rejected(tmp_path, run_dir):
    # run 20261013-131217: a full read of a 354 KB install.log overflowed the model's context window
    big, small = tmp_path / "install.log", tmp_path / "notes.txt"
    big.write_bytes(b"x" * 60_000)
    small.write_text("ok", encoding="utf-8")
    fs = lambda **a: check_tool_call("FileSystem", a, run_dir)
    assert "without 'limit' is not allowed" in fs(mode="read", path=str(big))
    assert fs(mode="read", path=str(big), offset=1, limit=200) is None
    assert fs(mode="read", path=str(small)) is None
    assert fs(mode="read", path=str(tmp_path / "missing.txt")) is None  # the tool reports missing files itself


def test_process_kill_only_for_msiexec(run_dir):
    assert check_tool_call("Process", {"mode": "list"}, run_dir) is None
    assert check_tool_call("Process", {"mode": "kill", "name": "msiexec.exe"}, run_dir) is None
    assert check_tool_call("Process", {"mode": "kill", "name": "devenv.exe"}, run_dir) is not None


def test_ui_tools_are_not_restricted(run_dir):
    assert check_tool_call("Click", {"label": 3}, run_dir) is None
    assert check_tool_call("App", {"mode": "switch", "name": "Any window"}, run_dir) is None


def test_sdk_guardrail_rejects_logs_and_traces(run_dir):
    run_dir.mkdir(parents=True)
    guard = tool_guardrail(run_dir, Trace(run_dir))
    data = lambda tool, args: SimpleNamespace(context=SimpleNamespace(tool_name=tool, tool_arguments=json.dumps(args)))

    allowed = guard.guardrail_function(data("Registry", {"mode": "get", "path": "HKLM:\\X"}))
    rejected = guard.guardrail_function(data("Registry", {"mode": "delete", "path": "HKLM:\\X"}))

    assert allowed.behavior["type"] == "allow"
    assert rejected.behavior["type"] == "reject_content" and "read-only" in rejected.behavior["message"]
    assert "guardrail_reject" in (run_dir / "trace.jsonl").read_text(encoding="utf-8")


INSTALL = (r"""Start-Process -FilePath msiexec.exe -ArgumentList '/i','"D:\in\x.msi"','/qn','/norestart','/l*v',"""
           r"""'"D:\run\evidence\install.log"' -Wait -PassThru""")


def test_install_runs_only_once_per_run(run_dir):
    # run 20261013-125224: the installer ran twice (the second time as a repair)
    policy = CallPolicy(run_dir)
    assert policy.check("PowerShell", {"command": INSTALL}) is None
    reason = policy.check("PowerShell", {"command": INSTALL + " | Select-Object -ExpandProperty ExitCode"})
    assert reason is not None and "install only once" in reason
    assert policy.check("PowerShell", {"command": r'Select-String -Path "D:\run\evidence\install.log" '
                                                  r'-Pattern "error status"'}) is None


def test_identical_calls_are_limited_but_looking_again_is_not(run_dir):
    # run 20261013-125224: FileSystem info on the same MSI 19 times
    policy = CallPolicy(run_dir)
    info = {"mode": "info", "path": r"D:\in\x.msi"}
    assert [policy.check("FileSystem", info) for _ in range(3)] == [None, None, None]
    assert "already made 3 times" in policy.check("FileSystem", info)
    assert policy.check("FileSystem", {"mode": "info", "path": r"D:\in\other.msi"}) is None
    assert all(policy.check("Snapshot", {"use_vision": True}) is None for _ in range(10))


def test_policy_still_applies_static_rules(run_dir):
    assert "read-only" in CallPolicy(run_dir).check("Registry", {"mode": "delete", "path": r"HKLM:\X"})



# ---------------------------------------------------------------- host rules (LOAD_TESTS_PLAN.md L7, L9, L13, L14)
HOST = HostLaunch(executable=r"C:\Program Files\Vendor\Host 2027\host.exe", args=["/product", "X", "/language", "en-US"],
                  processes=["host.exe"], main_window="^Host", new_document="Doc1")
LAUNCH = {"mode": "launch_executable", "executable": HOST.executable, "args": HOST.args}


def test_app_starts_only_the_host_with_its_exact_args(run_dir):
    app = lambda args, host=HOST: check_tool_call("App", args, run_dir, host)
    assert app(LAUNCH) is None
    assert app({**LAUNCH, "executable": HOST.executable.lower().replace("\\", "/")}) is None  # same path
    assert app({**LAUNCH, "args": '/product X /language "en-US"'}) is None  # args as one string
    assert "exactly" in app({**LAUNCH, "args": ["/language", "en-US"]})  # e.g. without /product: another product
    assert "exactly" in app({**LAUNCH, "executable": r"C:\Windows\System32\control.exe"})
    assert "not allowed" in app({"mode": "launch", "name": "Notepad"})  # by Start menu name
    assert "may not start programs" in app(LAUNCH, host=None)
    assert "may not start programs" in app(LAUNCH, host=HostLaunch(None, [], ["host.exe"], "^Host", "Doc1"))
    assert app({"mode": "resize", "window_size": [800, 600]}) is None


def test_process_kill_allows_host_processes_by_name_only(run_dir):
    kill = lambda **a: check_tool_call("Process", {"mode": "kill", **a}, run_dir, HOST)
    assert kill(name="host.exe") is None and kill(name="HOST") is None and kill(name="msiexec") is None
    assert "only allowed" in kill(name="devenv.exe")
    assert "pid is not allowed" in kill(pid=1234)
    assert "only allowed" in check_tool_call("Process", {"mode": "kill", "name": "host.exe"}, run_dir)  # no host


def test_waits_are_capped_below_the_tool_timeout(run_dir):
    wait = lambda tool, **a: check_tool_call(tool, a, run_dir, None, 105)
    assert wait("WaitFor", condition="active_window", window_name="Host", timeout=105) is None
    assert "call again" in wait("WaitFor", condition="active_window", window_name="Host", timeout=180)
    assert "maximum of 105" in wait("Wait", duration=300)
    assert wait("Wait", duration=5) is None and wait("WaitFor", condition="text_exists", text="x") is None


UNINSTALL = ("Start-Process -FilePath msiexec.exe -ArgumentList '/x','" + GUID + "','/qn','/norestart','/l*v',"
             r"""'"D:\run\evidence\uninstall.log"' -Wait""")


def test_no_uninstall_while_the_host_runs(run_dir):
    running = {"yes": True}
    policy = CallPolicy(run_dir, HOST, 105, host_running=lambda: running["yes"])
    reason = policy.check("PowerShell", {"command": UNINSTALL})
    assert reason is not None and "kill it first" in reason and "host.exe" in reason
    running["yes"] = False
    assert policy.check("PowerShell", {"command": UNINSTALL}) is None
    assert CallPolicy(run_dir).check("PowerShell", {"command": UNINSTALL}) is None  # no host in this run


def test_host_may_not_start_before_the_installer_ran(run_dir):
    # run 20261013-175002: Agent 2 started the host first and never installed the app
    policy = CallPolicy(run_dir, HOST, 105)
    assert "installer hasn't run yet" in policy.check("App", LAUNCH)
    assert policy.check("App", {"mode": "switch", "name": "Host"}) is None  # window focus is fine
    assert policy.check("PowerShell", {"command": INSTALL}) is None
    assert policy.check("App", LAUNCH) is None and policy.check("App", LAUNCH) is None  # a restart after a crash
