"""What an app leaves behind after its uninstall (built-in test UNIN-000, ARCHITECTURE.md D64).

Code lists the places apps write to (registry Software keys and the usual data and program folders) two levels
deep, once in the preflight before the install and once after Agent 2, after the host was closed. Entries that
are new and still there after the uninstall are leftovers:
  program leftovers   in the app's install folders or machine-wide places (HKLM, ProgramData, Program Files) -> FAIL
  settings leftovers  per-user data (HKCU, AppData, LocalAppData) -> PASS with a finding
Read-only: nothing is ever deleted. A diff only sees what was created during this run; leftovers from an earlier
install are already in the baseline (clean machines are a later phase, ADR-010).
"""

import json
import os
import re
import winreg
from pathlib import Path

from mpagent.models import KeyValue, Observation

BEFORE_FILE = "footprint_before.json"
LEFTOVERS_FILE = "evidence/leftovers.txt"
BUILT_IN_UNIN_ID = "UNIN-000"
DEPTH = 2
REGISTRY_ROOTS = (("HKCU", winreg.HKEY_CURRENT_USER, r"Software"),
                  ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE"),
                  ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node"))
USER_FOLDERS = ("APPDATA", "LOCALAPPDATA")
MACHINE_FOLDERS = ("ProgramData", "ProgramFiles", "ProgramFiles(x86)")
# Windows' own churn, never an app's leftover: exact places, so an app folder whose path happens to contain
# e.g. "Temp" still counts
WINDOWS_PLACES = (("LOCALAPPDATA", "Temp"), ("LOCALAPPDATA", "Microsoft"), ("LOCALAPPDATA", "Packages"),
                  ("LOCALAPPDATA", "CrashDumps"), ("LOCALAPPDATA", "D3DSCache"),  # DirectX shader cache
                  ("APPDATA", "Microsoft"), ("ProgramData", "Microsoft"))
WINDOWS_KEYS = (r"REG:HKCU\Software\Classes", r"REG:HKCU\Software\Microsoft", r"REG:HKLM\SOFTWARE\Classes",
                r"REG:HKLM\SOFTWARE\Microsoft", r"REG:HKLM\SOFTWARE\WOW6432Node\Classes",
                r"REG:HKLM\SOFTWARE\WOW6432Node\Microsoft")


def _windows_prefixes() -> list[str]:
    folders = [f"{kind}:{os.environ[env]}\\{name}" for env, name in WINDOWS_PLACES if os.environ.get(env)
               for kind in ("DIR", "FILE")]
    return [p.casefold() for p in (*folders, *WINDOWS_KEYS)]


def _folders(install_roots: list[str]) -> list[tuple[str, bool]]:
    """(folder, is_user_data) pairs to list; the app's install roots count as program folders."""
    out = [(os.environ[n], True) for n in USER_FOLDERS if os.environ.get(n)]
    out += [(os.environ[n], False) for n in MACHINE_FOLDERS if os.environ.get(n)]
    out += [(os.path.expandvars(r), False) for r in install_roots]
    return out


def _list_dir(root: Path, depth: int) -> set[str]:
    found: set[str] = set()
    try:
        children = list(os.scandir(root))
    except OSError:
        return found
    for c in children:
        try:  # sockets, broken links and locked entries can't even be checked; skip them
            is_dir = c.is_dir(follow_symlinks=False)
        except OSError:
            continue
        found.add(f"{'DIR' if is_dir else 'FILE'}:{c.path}")
        if depth > 1 and is_dir:
            found |= _list_dir(Path(c.path), depth - 1)
    return found


def _list_key(hive_name: str, hive, path: str, depth: int) -> set[str]:
    found: set[str] = set()
    try:
        key = winreg.OpenKey(hive, path)
    except OSError:
        return found
    with key:
        for i in range(winreg.QueryInfoKey(key)[0]):
            try:
                sub = f"{path}\\{winreg.EnumKey(key, i)}"
            except OSError:
                continue
            found.add(f"REG:{hive_name}\\{sub}")
            if depth > 1:
                found |= _list_key(hive_name, hive, sub, depth - 1)
    return found


def take(install_roots: list[str]) -> set[str]:
    """The current footprint: registry keys and folder entries, DEPTH levels deep."""
    entries: set[str] = set()
    for name, hive, path in REGISTRY_ROOTS:
        entries |= _list_key(name, hive, path, DEPTH)
    for folder, _ in _folders(install_roots):
        entries |= _list_dir(Path(folder), DEPTH)
    return entries


def save_before(run_dir: Path, install_roots: list[str]) -> None:
    (run_dir / BEFORE_FILE).write_text(json.dumps(sorted(take(install_roots))), encoding="utf-8")


def is_user_setting(entry: str, install_roots: list[str]) -> bool:
    path = entry.split(":", 1)[1].casefold()
    if any(path.startswith(os.path.expandvars(r).casefold()) for r in install_roots):
        return False
    if entry.startswith("REG:"):
        return path.startswith("hkcu\\")
    return any(os.environ.get(n) and path.startswith(os.environ[n].casefold()) for n in USER_FOLDERS)


def leftovers(before: set[str], after: set[str], ignore: list[str] = ()) -> list[str]:
    """New entries, keeping only the top-most of nested ones, without Windows' and the host's own churn."""
    patterns = [re.compile(p, re.IGNORECASE) for p in ignore]
    windows = _windows_prefixes()

    def churn(e: str) -> bool:
        low = e.casefold()
        return any(low == w or low.startswith(w + "\\") for w in windows) or any(p.search(e) for p in patterns)

    new = sorted(e for e in after - before if not churn(e))
    top: list[str] = []
    for e in new:
        if not any(e.split(":", 1)[1].startswith(t.split(":", 1)[1] + "\\") for t in top):
            top.append(e)
    return top


def record_unin000(run_dir: Path, install_roots: list[str], ignore: list[str] = ()) -> Observation | None:
    """Compare with the preflight's baseline and return UNIN-000's observation (None without a baseline)."""
    before_path = run_dir / BEFORE_FILE
    if not before_path.exists():
        return None
    found = leftovers(set(json.loads(before_path.read_text(encoding="utf-8"))), take(install_roots), list(ignore))
    settings = [e for e in found if is_user_setting(e, install_roots)]
    program = [e for e in found if e not in settings]
    lines = [f"program leftover: {e}" for e in program] + [f"settings leftover: {e}" for e in settings]
    evidence = []
    if lines:
        (run_dir / LEFTOVERS_FILE).parent.mkdir(parents=True, exist_ok=True)
        (run_dir / LEFTOVERS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        evidence.append(LEFTOVERS_FILE)
    findings = ([f"Left behind after the uninstall (program files or machine-wide): {e.split(':', 1)[1]}" for e in program]
                + [f"Left behind after the uninstall (user settings): {e.split(':', 1)[1]}" for e in settings])
    return Observation(test_id=BUILT_IN_UNIN_ID, executed=True,
                       observed=[KeyValue(key="program_leftovers", value=len(program)),
                                 KeyValue(key="settings_leftovers", value=len(settings))],
                       evidence=evidence, findings=findings,
                       notes=f"compared {len(json.loads(before_path.read_text(encoding='utf-8'))):,} entries from "
                             f"before the install with the state after the uninstall; {len(found)} new entries left")
