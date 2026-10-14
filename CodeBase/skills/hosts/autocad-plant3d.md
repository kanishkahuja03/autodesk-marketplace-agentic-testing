---
name: autocad-plant3d
description: Host notes for AutoCAD Plant 3D (an AutoCAD-based Autodesk product). Knowledge only, never values found on a specific machine. Used by Agents 1 and 2; the host_process block is read by code.
host_process:
  locate:
    registry_root: 'HKLM:\SOFTWARE\Autodesk\AutoCAD'
    value: AcadLocation
    match_value: ProductName
    match: '^AutoCAD Plant 3D \d{4}'
  executable: acad.exe
  args: [/product, PLNT3D, /language, en-US]
  processes: [acad.exe]
  main_window: '^(Autodesk )?AutoCAD Plant 3D \d{4}'
  new_document: 'Drawing\d+(\.dwg)?'
---

# Host: AutoCAD Plant 3D (`host_id: autocad-plant3d`)

## How to recognise a Plant 3D plug-in
- The plug-in manifest `PackageContents.xml` has `RuntimeRequirements` with `Platform="Plant3D"`. That's the strongest evidence. (`PLNT3D` is the Autodesk Marketplace and launch product code, not the manifest value.)
- Documents name "AutoCAD Plant 3D", "Plant 3D", "P&ID" or "Plant 3D projects".
- A generic AutoCAD plug-in (manifest platform `AutoCAD` or several AutoCAD products) is not Plant 3D-specific. Choose this host only if the evidence points to Plant 3D.

## Versions and release numbers
| Product year | AutoCAD release | SeriesMin/SeriesMax in manifests |
|---|---|---|
| 2024 | R24.3 | R24.3 |
| 2025 | R25.0 | R25.0 |
| 2026 | R25.1 | R25.1 |
| 2027 | R26.0 | R26.0 |

A manifest's `SeriesMin`/`SeriesMax` range tells which releases a plug-in supports. Compare it with the versions the description claims, and raise an open question if they disagree.

## Detecting the host (Agent 2, read-only)
- Registry: under `HKLM:\SOFTWARE\Autodesk\AutoCAD\<release>\` (e.g. `R26.0`) there are product keys named `ACAD-<id>:<language>`. Plant 3D is the key whose `ProductName` value starts with `AutoCAD Plant 3D <year>`. Example verified for 2027: `ACAD-A117:409`, `ProductName = AutoCAD Plant 3D 2027 - English`. Other `ACAD-*` keys under the same release belong to other AutoCAD-based products.
- `AcadLocation` (a value of that product key) is the install folder → `${HOST_INSTALL_DIR}`. `acad.exe` is in that folder.
- Don't assume the folder. Always read it.

## Where plug-ins go
- AutoCAD-family plug-ins are **`.bundle` folders** containing `PackageContents.xml` and a `Contents\` subfolder. The autoloader scans:
  - `%ProgramFiles%\Autodesk\ApplicationPlugins` (all users);
  - `%AppData%\Autodesk\ApplicationPlugins` (current user);
  - `%ProgramData%\Autodesk\ApplicationPlugins` (older releases; may not exist on 2026 and later).
- The folder the app's installer targets is `${PLUGIN_DIR}`. Take it from the installer facts (`install_roots`, `files[*].install_path`).
- Note: `%AppData%` belongs to the user who runs the installer. With an elevated session it is still that user's profile.

## Content packs
Plant 3D content packs copy catalog files (`.pcat`, `.acat`) into the shared content folder. The default is `C:\AutoCAD Plant 3D <year> Content\`, but it can be moved. Treat it as `${CONTENT_DIR}`.

## LOAD tests (Agent 2; see the host-interaction skill)
Code gives you the exact executable path and arguments in "App under test". Items marked *(verify)* still have to be confirmed on the machine (FUNCTIONAL_TESTS_PLAN.md build step 1).

### Start
- `acad.exe` with `/product PLNT3D /language en-US` starts Plant 3D. Without `/product`, it starts plain AutoCAD instead, which is the wrong product. *(Verified 2027: the Start-menu shortcut "AutoCAD Plant 3D 2027 - English" uses exactly these arguments.)*
- Starting takes 30–90 s. A splash screen comes first, then the main window.

### Ready signal
- The main window's title starts with `AutoCAD Plant 3D <year>` (possibly after `Autodesk `). *(verify the exact title)*
- With no drawing open, the **Start** tab is shown and the ribbon is hidden. That's normal: open a new drawing (below).
- Plant 3D may reopen the last project in the Project Manager palette. Leave it as it is: don't open, close or change projects. *(verify)*

### Dialogs at start
Examples only. You decide how to handle each dialog (host-interaction skill, section 4).
- **Plug-in notices.** A plug-in may show its own message when Plant 3D starts. *Seen 2026-10-13/14:* a dialog titled "Hinweis" (German, "Notice") from a P&ID plug-in, saying it only works together with a companion product, with only OK. That's an information notice.
- **Load or security prompts** for a plug-in outside a trusted location (e.g. *"Security – Unsigned Executable File"*, or a question asking whether to load it). If it names the app under test, the one-time answer ("Load", "Load once", "Yes") fits. Never "Always load", and never change `SECURELOAD` or `TRUSTEDPATHS`. *(not seen yet)*
- **Licence, sign-in, "what's new" or update dialogs** belong to Autodesk, not to the app. Don't agree to anything there.
- After start, Plant 3D briefly shows `Drawing1.dwg` and then switches to its **Start** page. *Seen 2026-10-14.* That's not a dialog: open a new drawing (below).

### Default new document
- Press **Ctrl+N** in the main window (the `Shortcut` tool). If a "Select template" dialog opens, keep the default template and click **Open**. *(verify)*
- The new drawing is named `Drawing1.dwg` (or `Drawing2.dwg`, …). It appears as a document tab and in the main window title. *(verify)*

### Where app entry points appear
- Plug-in ribbon tabs appear next to the built-in tabs (Home, Insert, …) once a drawing is open, also in a plain drawing from the default template. *Seen 2026-10-14.*
- **Ribbon tabs are not in the Snapshot's UI tree** (only a "Ribbon" pane with two unnamed buttons is listed). *Seen 2026-10-13/14.* The screenshots are what shows them, so take one of every state.
- A plug-in tab can hold groups whose contents only show when the group or its drop-down is opened. Opening them only reveals the UI.
- Some plug-ins add their tab only in certain workspaces. *(not seen yet)*

### Close without saving (Phase 2)
In Phase 1 the host is closed with `Process kill` on `acad.exe` only. Never save a drawing.
