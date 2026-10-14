"""Tests for the preflight (ARCHITECTURE.md D20, D23). Run with: uv run pytest"""

import re
import winreg

import pytest

from mpagent.config import load_settings
from mpagent.execute import preflight
from mpagent.execute.observations import load_observations
from mpagent.models import InstallerFacts

FACTS = InstallerFacts(installer_file="x.msi", installer_type="msi", sha256="0", properties={
    "ProductCode": "{00000000-1111-2222-3333-444444444444}", "ProductName": "mpagent test app that does not exist"})


def any_installed_display_name() -> str | None:
    """A DisplayName that really exists under HKLM Uninstall on this machine (read-only)."""
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, preflight.UNINSTALL_KEYS[0][2]) as root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                    return winreg.QueryValueEx(k, "DisplayName")[0]
            except OSError:
                continue
    return None


def test_entry_not_found_for_unknown_app():
    assert preflight.find_uninstall_entry(FACTS.properties["ProductCode"], FACTS.properties["ProductName"]) is None


def test_entry_found_by_display_name():
    name = any_installed_display_name()
    if name is None:
        pytest.skip("no Uninstall entries with a DisplayName on this machine")
    assert preflight.find_uninstall_entry(None, name.upper()).startswith("HKLM:\\")


def test_env000_is_recorded_as_observation(tmp_path):
    obs = preflight.check_env000(tmp_path, FACTS)
    assert obs.observed[0].key == "preinstalled_entry_exists" and obs.observed[0].value is False
    assert load_observations(tmp_path) == [obs]


def test_not_elevated_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "is_elevated", lambda: False)
    with pytest.raises(preflight.PreflightError, match="not running as administrator"):
        preflight.run_preflight(tmp_path, FACTS, load_settings())


def test_already_installed_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "is_elevated", lambda: True)
    monkeypatch.setattr(preflight.asyncio, "run", lambda coro: (coro.close(), ["13 tools"])[1])
    monkeypatch.setattr(preflight, "find_uninstall_entry", lambda code, name: r"HKLM:\...\Uninstall\{X}")
    uninstall = re.escape(f"msiexec /x {FACTS.properties['ProductCode']} /qn")
    with pytest.raises(preflight.PreflightError, match=f"app already installed .*{uninstall}"):
        preflight.run_preflight(tmp_path, FACTS, load_settings())
    assert load_observations(tmp_path)[0].observed[0].value is True  # ENV-000 still recorded


def test_windows_mcp_failure_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "is_elevated", lambda: True)

    def broken(coro):
        coro.close()
        raise preflight.WindowsMcpError("tool list mismatch: extra=['Clipboard'] missing=-")
    monkeypatch.setattr(preflight.asyncio, "run", broken)
    with pytest.raises(preflight.PreflightError, match="Windows-MCP: tool list mismatch"):
        preflight.run_preflight(tmp_path, FACTS, load_settings())


def test_running_host_stops(tmp_path, monkeypatch):
    # FUNCTIONAL_TESTS_PLAN.md L12: a run would act in, and at the end kill, the user's own host session
    from mpagent.hostnotes import host_process

    monkeypatch.setattr(preflight, "is_elevated", lambda: True)
    monkeypatch.setattr(preflight.asyncio, "run", lambda coro: (coro.close(), ["13 tools"])[1])
    monkeypatch.setattr(preflight, "running_pids", lambda names: {4242: "acad.exe"})
    with pytest.raises(preflight.PreflightError, match=r"the host is running \(acad.exe PID 4242\)"):
        preflight.run_preflight(tmp_path, FACTS, load_settings(), host_process("autocad-plant3d"))
    monkeypatch.setattr(preflight, "running_pids", lambda names: {})
    preflight.run_preflight(tmp_path, FACTS, load_settings(), host_process("autocad-plant3d"))
