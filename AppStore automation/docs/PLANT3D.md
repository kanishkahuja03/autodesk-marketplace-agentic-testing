# Plant 3D — PoC host notes

Engineering notes for **AutoCAD Plant 3D** as the certification host. Generic requirements remain in [SPEC.md](./SPEC.md).

## Version

- **Target version:** _TBD_ (e.g. Plant 3D 2025 on Windows).
- Record exact build and AutoCAD core version in `test_data/catalogue.json` when fixed.

## Disciplines

Plant 3D spans multiple contexts; tests must open the correct context:

| Context | Typical test asset | Notes |
|---------|-------------------|--------|
| P&ID | 2D DWG with P&ID objects | Project/spec may be required |
| 3D piping | 3D plant DWG | May need project setup |

Tag each catalogue entry with `discipline: pid | 3d` and allowed commands.

## Environment reset

1. Revert VM snapshot **or** run cleanup script:
   - Uninstall / reinstall plugin if needed
   - Remove copied project folders under a fixed sandbox root
   - Restore golden `test_data/projects/<id>` from zip
2. Avoid relying on `%LOCALAPPDATA%` paths without resetting them between runs.

## Plugin load verification

Confirm with SME; candidates:

- AutoCAD `APPLOAD` / `.NET` assembly loaded list
- Publisher-documented smoke command
- Registry or install folder markers

Implement as tool `verify_plugin_loaded`—method documented here once chosen.

## Automation preferences

1. **`run_command`** and AutoCAD .NET automation where stable.
2. UI automation (ribbon/dialog) only for gaps with screenshot evidence.
3. Always **`wait_for_idle`** after commands with bounded timeout.

## Test data catalogue (initial)

To be populated under `test_data/`:

| `dataset_id` | Discipline | Description | Expected open |
|--------------|------------|-------------|---------------|
| `pid_small_01` | pid | Small P&ID sample | TBD |
| `plant3d_small_01` | 3d | Small 3D model | TBD |

Each entry includes: file paths, optional project folder, supported `host_versions`, approved tools.

## Example PoC workflow (template)

Replace with pilot plugin steps from publisher docs:

1. Open `dataset_id` DWG.
2. Run documented command (export / validate / catalog operation).
3. Verify output file or log line.
4. Capture screenshot and logs.

## Licensing

- Document whether automation runs under named user, network license, or dedicated entitlement.
- Blocker if headless/VM session cannot obtain license—resolve before Phase 1 sign-off.

## Compatibility matrix

Generic checks must validate submission `host_versions[]` against the VM template. Unsupported version → **Fail** fast with clear report message (no install attempt if policy forbids).
