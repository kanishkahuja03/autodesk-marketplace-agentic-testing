"""Cleanup (ARCHITECTURE.md D28): code, run in `finally` once Agent 2 has started.

If the app is still installed at the end (its Uninstall entry still exists, so UNIN didn't complete),
remove it silently with msiexec so the next run doesn't stop at ENV-000. It never changes a verdict.
"""

import subprocess
from pathlib import Path

from mpagent.execute.preflight import find_uninstall_entry
from mpagent.models import InstallerFacts
from mpagent.runlog import log

CLEANUP_TIMEOUT_S = 600


def cleanup(run_dir: Path, facts: InstallerFacts) -> None:
    code, name = facts.properties.get("ProductCode"), facts.properties.get("ProductName")
    entry = find_uninstall_entry(code, name)
    if entry is None:
        log.info("CLEANUP: nothing to do, the app is not installed")
        return
    if facts.installer_type != "msi" or not code:
        log.warning("CLEANUP: the app is still installed (%s) and isn't an MSI with a ProductCode — "
                    "manual cleanup needed", entry)
        return

    log_path = run_dir / "evidence" / "cleanup.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log.warning("CLEANUP: the app is still installed (%s); running msiexec /x %s /qn", entry, code)
    try:
        proc = subprocess.run(["msiexec.exe", "/x", code, "/qn", "/norestart", "/l*v", str(log_path)],
                              timeout=CLEANUP_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error("CLEANUP: msiexec failed to run: %s — manual cleanup needed", e)
        return
    still = find_uninstall_entry(code, name)
    if still:
        log.error("CLEANUP: msiexec exit code %d but the app is still installed — manual cleanup needed",
                  proc.returncode)
    else:
        log.info("CLEANUP: done (msiexec exit code %d, log evidence/cleanup.log)", proc.returncode)
