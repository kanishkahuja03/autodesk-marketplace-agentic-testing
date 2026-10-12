---
name: autocad-plant3d
description: Host notes for AutoCAD Plant 3D (an AutoCAD-based Autodesk product). Knowledge only, never values found on a specific machine. Used by Agents 1 and 2.
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

## Not in scope for ENV/INST/UNIN
Launching Plant 3D, the ribbon, commands and projects. Those are LOAD/FUNC tests, which come later.
