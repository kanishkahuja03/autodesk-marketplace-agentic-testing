"""Preflight (ARCHITECTURE.md D20, D23): code checks run after Agent 1 and before Agent 2.

1. The process is elevated (installers and the UI uninstall need admin; UAC can't be automated).
2. Windows-MCP starts and exposes exactly the 13 allowed tools.
3. ENV-000: the app is not installed yet (Uninstall entry by ProductCode, or DisplayName as a fallback).
Any failure raises PreflightError; the pipeline then stops and Agent 2 doesn't start.
"""

import asyncio
import ctypes
import winreg
from pathlib import Path

from mpagent.config import Settings
from mpagent.design.selfcheck import BUILT_IN_ENV_ID
from mpagent.execute.observations import save_observation
from mpagent.execute.windows_mcp import (
    WindowsMcpError,
    check_tool_list,
    windows_mcp_server,
)
from mpagent.models import InstallerFacts, KeyValue, Observation
from mpagent.runlog import log

UNINSTALL_KEYS = (
    (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, "HKCU", r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)


class PreflightError(Exception):
    """A preflight check failed; the message is the STOPPED reason."""


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def find_uninstall_entry(product_code: str | None, display_name: str | None) -> str | None:
    """Registry path of the app's Uninstall entry, or None. Read-only."""
    for hive, hive_name, base in UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(hive, base)
        except OSError:
            continue
        with root:
            if product_code:
                try:
                    winreg.OpenKey(root, product_code).Close()
                    return rf"{hive_name}:\{base}\{product_code}"
                except OSError:
                    pass
            if display_name:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    sub = winreg.EnumKey(root, i)
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            name, _ = winreg.QueryValueEx(k, "DisplayName")
                    except OSError:
                        continue
                    if str(name).strip().casefold() == display_name.strip().casefold():
                        return rf"{hive_name}:\{base}\{sub}"
    return None


def check_env000(run_dir: Path, facts: InstallerFacts) -> Observation:
    """Run the built-in ENV-000 and record its observation in observations.json."""
    code, name = facts.properties.get("ProductCode"), facts.properties.get("ProductName")
    found = find_uninstall_entry(code, name)
    obs = Observation(
        test_id=BUILT_IN_ENV_ID, executed=True,
        observed=[KeyValue(key="preinstalled_entry_exists", value=found is not None)],
        evidence=[], notes=f"found {found}" if found else f"no Uninstall entry for ProductCode {code} / '{name}'",
    )
    save_observation(run_dir, obs)
    return obs


async def _check_mcp(settings: Settings) -> list[str]:
    async with windows_mcp_server(settings) as server:
        return await check_tool_list(server)


def run_preflight(run_dir: Path, facts: InstallerFacts, settings: Settings) -> None:
    if not is_elevated():
        raise PreflightError("not running as administrator — start Visual Studio as administrator")
    log.info("  elevated: yes")

    try:
        tools = asyncio.run(_check_mcp(settings))
    except WindowsMcpError as e:
        raise PreflightError(f"Windows-MCP: {e}") from e
    except Exception as e:
        raise PreflightError(f"Windows-MCP could not start: {type(e).__name__}: {e}") from e
    log.info("  Windows-MCP: %d allowed tools", len(tools))

    obs = check_env000(run_dir, facts)
    log.info("  ENV-000: %s", obs.notes)
    if obs.observed[0].value:
        code = facts.properties.get("ProductCode")
        how = (f"in an administrator prompt run: msiexec /x {code} /qn" if facts.installer_type == "msi" and code
               else "use Control Panel > Programs and Features")
        raise PreflightError(f"app already installed ({obs.notes}) — uninstall it first ({how}), then run again")
