"""The host application on this machine (FUNCTIONAL_TESTS_PLAN.md L9, L12, L13): find its executable,
see whether it runs, and kill it. Driven only by the host notes' `host_process` front matter.

Read-only except kill_host(), which code calls in `finally` (before cleanup) so an uninstall never runs
under a running host. The preflight refuses to start while the host runs, so every host process found
later was started during this run.
"""

import csv
import io
import json
import re
import subprocess
import winreg
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mpagent.models import HostProcess
from mpagent.runlog import log

HIVES = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
         "HKCU": winreg.HKEY_CURRENT_USER, "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER}
KILL_TIMEOUT_S = 60
CRASH_EVENTS_FILE = "evidence/host_crash_events.txt"
# Windows writes these for every application crash, whatever the product (run 20261013-175002)
CRASH_PROVIDERS = ("Application Error", "Windows Error Reporting", ".NET Runtime")


@dataclass(frozen=True)
class HostLaunch:
    """What Agent 2 may start and kill, resolved on this machine. `executable` is None if not found."""

    executable: str | None
    args: list[str]
    processes: list[str]
    main_window: str
    new_document: str


def find_install_dir(hp: HostProcess) -> Path | None:
    """The folder in registry value `locate.value` of the first product key (up to 2 levels below
    `locate.registry_root`) whose `locate.match_value` matches `locate.match`."""
    hive_name, _, sub = hp.locate.registry_root.replace(":", "").partition("\\")
    hive = HIVES.get(hive_name.upper())
    if hive is None:
        return None
    pattern = re.compile(hp.locate.match)

    def search(key_path: str, depth: int) -> Path | None:
        try:
            key = winreg.OpenKey(hive, key_path)
        except OSError:
            return None
        with key:
            try:
                if pattern.search(str(winreg.QueryValueEx(key, hp.locate.match_value)[0])):
                    return Path(winreg.QueryValueEx(key, hp.locate.value)[0])
            except OSError:
                pass
            if depth == 0:
                return None
            for i in range(winreg.QueryInfoKey(key)[0]):
                found = search(f"{key_path}\\{winreg.EnumKey(key, i)}", depth - 1)
                if found:
                    return found
        return None

    return search(sub, 2)


def resolve(hp: HostProcess) -> HostLaunch:
    folder = find_install_dir(hp)
    exe = folder / hp.executable if folder else None
    return HostLaunch(executable=str(exe) if exe and exe.is_file() else None, args=list(hp.args),
                      processes=list(hp.processes), main_window=hp.main_window, new_document=hp.new_document)


def running_pids(processes: list[str]) -> dict[int, str]:
    """PID -> image name of every running process with one of these image names."""
    wanted = {_image(p) for p in processes}
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=30,
                             check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    found = {}
    for row in csv.reader(io.StringIO(out)):
        if len(row) >= 2 and _image(row[0]) in wanted and row[1].isdigit():
            found[int(row[1])] = row[0]
    return found


def kill_host(processes: list[str]) -> list[int]:
    """Force-kill every running host process (no graceful close: it would wait on 'Save changes?')."""
    killed = []
    for pid, name in running_pids(processes).items():
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=KILL_TIMEOUT_S,
                           check=False)
            killed.append(pid)
            log.info("HOST: killed %s (PID %d)", name, pid)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.error("HOST: could not kill %s (PID %d): %s", name, pid, e)
    return killed


def crash_events(processes: list[str], since: datetime) -> list[str]:
    """Windows Application-log crash records (provider, time, message) that name one of the host's
    processes, written since `since`. Read-only; empty if the log can't be read."""
    images = sorted({_image(p) for p in processes})
    script = ("Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=[datetime]'" + since.isoformat() +
              "'} -ErrorAction SilentlyContinue | Where-Object { @('" + "','".join(CRASH_PROVIDERS) +
              "') -contains $_.ProviderName } | "
              "Select-Object @{n='Time';e={$_.TimeCreated.ToString('s')}}, ProviderName, Message | "
              "ConvertTo-Json -Depth 2")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=60, check=False).stdout.strip()
        items = json.loads(out) if out else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    found = []
    for e in items if isinstance(items, list) else [items]:
        message = str(e.get("Message") or "")
        if any(img in message.casefold() for img in images):
            found.append(f"[{e.get('Time')}] {e.get('ProviderName')}\n{message.strip()}")
    return found


def save_crash_events(run_dir: Path, processes: list[str], since: datetime) -> list[str]:
    """Write the host's crash records to evidence/host_crash_events.txt (only if there are any)."""
    events = crash_events(processes, since)
    if events:
        path = run_dir / CRASH_EVENTS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n\n".join(events) + "\n", encoding="utf-8")
    return events


def _image(name: str) -> str:
    name = name.strip().casefold()
    return name if name.endswith(".exe") else name + ".exe"
