---
name: none
description: Host notes for a standalone Windows app that doesn't plug into another application. Used by Agents 1 and 2.
---

# Host: none (standalone Windows app, `host_id: none`)

Use this when the app runs on its own (it has its own executable and isn't loaded by another program).

## What applies
- **No host tests.** ENV covers only what the app's documents require (e.g. 64-bit Windows, a minimum Windows version, free disk space).
- Typical install footprint, all taken from the installer facts:
  - program files under `%ProgramFiles%\<Publisher or App>\` (per-machine) or `%LocalAppData%\Programs\<App>\` (per-user);
  - Start menu shortcuts under `%ProgramData%\Microsoft\Windows\Start Menu\Programs\` or `%AppData%\Microsoft\Windows\Start Menu\Programs\`;
  - a Programs and Features (Uninstall) entry.
- The install folder is `${PLUGIN_DIR}` (the same placeholder name keeps the rules simple), resolved by Agent 2 from the Uninstall entry's `InstallLocation` or from the installer facts.

## Not in scope for ENV/INST/UNIN
Starting the app and using its features. Those are LOAD/FUNC tests, which come later.
