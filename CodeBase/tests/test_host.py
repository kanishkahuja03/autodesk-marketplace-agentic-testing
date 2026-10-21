"""Tests for finding, checking and killing the host (LOAD_TESTS_PLAN.md L9, L12, L13). Run with: uv run pytest"""

import subprocess
from datetime import UTC, datetime

import pytest

from mpagent.execute import host
from mpagent.hostnotes import host_process

TASKLIST = ('"System Idle Process","0","Services","0","8 K"\n'
            '"acad.exe","4242","Console","1","900,000 K"\n'
            '"ACAD.EXE","4343","Console","1","10 K"\n'
            '"devenv.exe","5000","Console","1","500,000 K"\n')


def test_running_pids_matches_image_names(monkeypatch):
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=TASKLIST))
    assert host.running_pids(["acad.exe"]) == {4242: "acad.exe", 4343: "ACAD.EXE"}
    assert host.running_pids(["acad"]) == {4242: "acad.exe", 4343: "ACAD.EXE"}
    assert host.running_pids(["notepad.exe"]) == {}


def test_kill_host_force_kills_each_host_process(monkeypatch):
    killed = []

    def fake_run(cmd, **_kw):
        if cmd[0] == "tasklist":
            return subprocess.CompletedProcess(cmd, 0, stdout=TASKLIST)
        assert cmd[:2] == ["taskkill", "/F"]
        killed.append(int(cmd[-1]))
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(host.subprocess, "run", fake_run)
    assert host.kill_host(["acad.exe"]) == [4242, 4343] and killed == [4242, 4343]  # never devenv.exe


def test_registry_lookup_with_a_host_that_does_not_exist():
    hp = host_process("autocad-plant3d").model_copy(deep=True)
    hp.locate.match = "^No Such Product 9999$"
    assert host.find_install_dir(hp) is None
    assert host.resolve(hp).executable is None


def test_real_host_resolves_if_installed():
    resolved = host.resolve(host_process("autocad-plant3d"))
    if resolved.executable is None:
        pytest.skip("AutoCAD Plant 3D is not installed on this machine")
    assert resolved.executable.lower().endswith("acad.exe") and resolved.args[:2] == ["/product", "PLNT3D"]


EVENTS = ('[{"Time": "2026-10-13T17:50:46", "ProviderName": "Application Error", "Message": "Faulting application '
          'name: acad.exe, version: 32.0.118.0\\nFaulting module name: ODISSDK.dll"},'
          ' {"Time": "2026-10-13T17:51:00", "ProviderName": "Application Error", "Message": "Faulting application '
          'name: devenv.exe"}]')


def test_crash_events_keep_only_the_hosts_processes(monkeypatch, tmp_path):
    # run 20261013-175002: the host crashed in ODISSDK.dll; Windows had the record, the run didn't
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=EVENTS))
    events = host.save_crash_events(tmp_path, ["acad.exe"], datetime(2026, 10, 13, 17, 50, tzinfo=UTC))
    assert len(events) == 1 and events[0].startswith("[2026-10-13T17:50:46] Application Error")
    assert "ODISSDK.dll" in (tmp_path / host.CRASH_EVENTS_FILE).read_text(encoding="utf-8")
    one = EVENTS[1:EVENTS.index("},") + 1]  # PowerShell returns a single object, not a list, for one event
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=one))
    assert len(host.crash_events(["acad"], datetime(2026, 10, 13, tzinfo=UTC))) == 1
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=""))
    assert host.save_crash_events(tmp_path / "x", ["acad.exe"], datetime(2026, 10, 13, tzinfo=UTC)) == []
    assert not (tmp_path / "x").exists()  # no file without crashes
