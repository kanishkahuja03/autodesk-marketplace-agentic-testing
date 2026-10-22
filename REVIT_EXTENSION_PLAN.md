# Revit Extension Plan (draft, before grill-me)

Status: **Grilled 2026-10-21.** The decisions are in §9 and recorded as ADR-048 (`ADR.md`) and D68 (`ARCHITECTURE.md` §2.6). Values that need Revit 2027 installed (registry, window titles, UI Automation tree) come next.

## 1. Goal
Add Autodesk Revit as a second host after AutoCAD Plant 3D. The same two-agent pipeline should validate a free App Store plug-in for Revit with no authentication. No Revit-specific logic goes into the pipeline code (ADR-001 / D1, ADR-046 / D67). Host knowledge stays in data files, as it does for Plant 3D.

## 2. Current state (how Plant 3D is wired)
Plant 3D is almost all data:

| Piece | File |
|---|---|
| Host profile (front matter only) | `CodeBase/skills/hosts/autocad-plant3d.md` |
| Navigation prose for Agent 2 | `CodeBase/skills/hosts/navigation/plant3d-navigation.md` |
| Step sequences for `find_ui` / `click_ui` / `type_ui` | `CodeBase/skills/hosts/navigation/plant3d-navigation-steps.md` |
| Sample project | `SAMPLES_DIR` in `CodeBase/.env` (single global path) |

- Agent 1 picks `host_id` from the catalogue of `skills/hosts/*.md` (ADR-012 / D15). There is no CLI flag and no keyword-matching code.
- Everything downstream reads `host_process` through `hostnotes.py`: launch, kill, preflight, guardrails, crash records, UI-tree scoping, UI-find, LOAD-000, verdict, footprint.

### Gaps that block Revit
1. **Installer read only understands `PackageContents.xml`.**
   - `design/static_read.py` does not unpack or read `.addin` manifests from an MSI.
   - `design/intake.py` rejects a zip that has no `PackageContents.xml`.
2. **`install_root()`** (`static_read.py`) keeps 3 path parts. For Revit that turns `%ProgramData%\Autodesk\Revit\Addins\<ver>\x.addin` into `%ProgramData%\Autodesk\Revit`, which is too broad for the footprint and UNIN-000.
3. **`SAMPLES_DIR` is global** and points at the Plant 3D SampleProject. It is not tied to a host.
4. **`tests/test_skills.py`** bans the word `revit` in all skill prose (:93) and in navigation files (:125). `EXPECTED` (:13) lists only the Plant 3D profile.
5. **LOAD-000 without a sample** expects a default new document. Revit opens on a Home screen, and a new project goes through a template dialog.
6. **All navigation content is AutoCAD-specific**: command line, `OPEN`/`CLOSE`, Project Manager.
7. **`BundleComponent.load_on_startup`** reads the AutoCAD-named attribute `LoadOnAutoCADStartup`. This is harmless for Revit, but the name is not generic.

## 3. Target plug-in

The criteria: free, standard App Store installer, no login, licence or online service, works offline, results visible in the UI, supports a recent Revit version.

| Role | Plug-in | Publisher | Revit | What it does | Why |
|---|---|---|---|---|---|
| **Primary** | [Tiny Tools](https://marketplace.autodesk.com/apps/d90f49ca-1ad8-4a4b-b2e5-1497cf305c58) | Archilizer | 2022–2027 | Duplicate Views, Bulk Rename, Sheets from Views, Duplicate Sheets, Align Views | Dialogs only. Results show in the Project Browser with predictable names. |
| Backup | [Schedule Plus](https://marketplace.autodesk.com/apps/6e379167-8821-4b15-b2de-50f0e58fb3c3) | Pangolin tools | 2020–2026 | Exports schedules to `.xlsx` | The output file can be checked. No 2027 support. Not yet verified whether it needs Excel. |
| Later | ElementRenumbering | Juan Osborne | 2022–2027 | Renumbers elements | You pick elements in the canvas, so it is a harder test. |

**Rejected:**

| Plug-in | Reason |
|---|---|
| SheetEX | Online licence check after 30 days |
| Xrev Freebies, NonicaTab FREE, CTC suites | Custom installers |
| SiruS Export Schedules, Schedule To Excel (SALEM), Pangolin Unhide | No support beyond Revit 2024 |

Caveat: "no auth" is based only on the listing text. It is confirmed only once the plug-in has been installed and run.

## 4. Revit facts the agents need (to be checked on the machine)
- **Executable:** `C:\Program Files\Autodesk\Revit <year>\Revit.exe`. Process: `Revit.exe`.
- **Add-ins:**
  - `.addin` manifests go in `C:\ProgramData\Autodesk\Revit\Addins\<year>\` (all users) or `%AppData%\Autodesk\Revit\Addins\<year>\` (per user).
  - Store bundles go in `ApplicationPlugins\<App>.bundle` with `PackageContents.xml`, gated by `SeriesMin` / `SeriesMax` (`R20xx`).
- **First load of an unsigned add-in** shows the modal dialog **"Security – Unsigned Add-in"** (Always Load / Load Once / Do Not Load). Agent 2 must handle it.
- **Ribbon:** a single-panel add-in goes on the **Add-Ins** tab. Multi-panel add-ins get their own tab.
  - The ribbon is WPF (AdWindows), and UI Automation can see it, unlike the AutoCAD ribbon.
  - The model canvas is opaque to UI Automation, so use screenshots for canvas state.
- **Home screen:** Revit 2025+ opens on a full-window Home screen. Opening a model switches to the ribbon UI.
- **Licensing:** a named-user licence needs a sign-in and internet on first launch, and allows up to 30 days offline. The user signs in once by hand. A sign-in window during a run is treated as **blocked**.
- **Sample files:** for 2025 and later they are downloaded, not installed (e.g. `rac_basic_sample_project.rvt`). Older versions used `C:\Program Files\Autodesk\Revit <year>\Samples`.

## 5. Plan

### Phase 1: prerequisites (user)
1. Install Revit, sign in once, and dismiss the first-run prompts.
2. Download the target plug-in's installer and documentation into `CodeBase/inputs/<app>/`.
3. Download the sample model (`rac_basic_sample_project.rvt`).
4. Probe the machine to capture real values:
   - registry keys (locate block);
   - window titles (`main_window`, `new_document`);
   - the UI Automation tree of the Home screen, ribbon, Project Browser, Open dialog and Security dialog.

### Phase 2: data and generic code changes
1. **Host profile** `CodeBase/skills/hosts/revit.md`, front matter only:
   - `releases`, e.g. `'2027': R2027`;
   - `host_process`: locate, executable, args, processes, `main_window`, `new_document`, optional `profile_ignore`;
   - `navigation` and `navigation_steps`.
2. **Navigation files** `navigation/revit-navigation.md` and `navigation/revit-navigation-steps.md`. They cover:
   - the Home screen;
   - opening an `.rvt` (Open dialog, `File name:`);
   - Project Browser tree items;
   - ribbon tabs, with click-by-name where UI Automation exposes them and "Screenshot only" where it does not;
   - the Security – Unsigned Add-in prompt (Always Load);
   - closing without saving.
3. **Installer evidence:** unpack `.addin` files from MSI and zip installers. Pass them to Agent 1 as raw evidence, like documents, with no Revit parser. Let `intake.py` accept a zip that contains `.addin` files.
4. **Generic `install_root()`:** derive the footprint root so the Revit `Addins\<ver>` paths stay narrow, without breaking the `ApplicationPlugins` case.
5. **Per-host sample path:** replace the global `SAMPLES_DIR` with a host-specific value, so Revit is never offered the Plant 3D project. Where it lives is open (§6, question 3).
6. **`tests/test_skills.py` genericity rule:** allow host and product names only inside that host's own profile and navigation files. Generic skills stay strict. Add `hosts/revit.md` to `EXPECTED`.
7. **(Optional)** Rename `load_on_startup` or `LoadOnAutoCADStartup` handling to a neutral name.

### Phase 3: tests and verification
1. Add unit tests with Revit fixtures:
   - host profile parse;
   - navigation and steps load;
   - `.addin` evidence;
   - `install_root`;
   - per-host sample choice;
   - a selfcheck `host_id` example (replacing the current use of "revit" as the invalid id at `test_selfcheck.py:91`).
2. Run `uv run pytest` from `CodeBase/`. All tests must pass.
3. Do a full pipeline run on Tiny Tools:
   - INST, LOAD-000 opening the sample, FUNC tests on Project Browser results, UNIN-000;
   - review the report and evidence.

### Phase 4: documentation (after grill-me)
- Record the decisions in `ADR.md` (new ADRs) and `ARCHITECTURE.md`. In particular, correct the "a new host is one Markdown file" statement (ARCHITECTURE.md:361) and the `BundleManifest` note (ARCHITECTURE.md:178).

## 6. Open questions (for grill-me)
1. **Revit version:** 2027 (Tiny Tools) or 2026 (also Schedule Plus)? Proposed: 2027.
2. **Target plug-in:** Tiny Tools as primary? Proposed: yes.
3. **Sample location:** in the host profile front matter (machine path in a checked-in file), a per-host `.env` key, or `inputs/<app>/sample/`? Proposed: host profile key, overridable from `.env`.
4. **`.addin` handling:** raw evidence for Agent 1, or a dedicated reader that produces typed facts? Proposed: raw evidence.
5. **Security – Unsigned Add-in prompt:** navigation guidance only, or also a guardrail, or a preflight that pre-trusts the add-in? Proposed: navigation guidance, with Agent 2 clicking Always Load.
6. **LOAD-000 for Revit:** always open the sample (skip the Home screen and the template dialog)? Proposed: yes, when a sample exists.
7. **Sign-in or licence window during a run:** stop as blocked, or let it fail? Proposed: blocked, with evidence.
8. **Genericity test change:** is a per-host allowlist acceptable under ADR-046 / D67?

## 7. Risks
- Revit's registry layout may not fit `find_install_dir` (2 levels, one value for the folder, one name regex).
- The UI Automation tree of the ribbon or Project Browser may differ from the research. Probing in Phase 1 reduces this risk.
- Tiny Tools has little documentation (listing text only), so Agent 1 may produce few cited FUNC tests.
- The store download needs an Autodesk sign-in, which the user does by hand.

## 8. Sources
- Revit publisher guidelines: https://aps.autodesk.com/marketplace/publisher-center/revit-publisher-guidelines
- SeriesMin / SeriesMax: https://blog.autodesk.io/revit-api-understanding-the-role-of-seriesmin-and-seriesmax-in-plugin-deployment/
- Add-in manifest locations: https://help.autodesk.com/cloudhelp/2016/ENU/Revit-API/files/GUID-4FFDB03E-6936-417C-9772-8FC258A261F7.htm
- Unsigned add-in prompt: https://forums.autodesk.com/t5/revit-api-forum/code-signing-of-revit-addins/m-p/6316552
- Sample project files (2026): https://help.autodesk.com/view/RVT/2026/ENU/?guid=GUID-61EF2F22-3A1F-4317-B925-1E85F138BE88
- Licensing / offline: https://www.autodesk.com/support/account/admin/licensing-faq/authorization
- Ribbon UI Automation: https://blog.autodesk.io/thin-lines-add-in-using-ui-automation/

## 9. Grill-me decisions (2026-10-21)

| # | Question | Decision |
|---|---|---|
| G1 | Revit version and plug-ins | **Revit 2027** (free trial for now). Primary: **Tiny Tools**. Backup: **ElementRenumbering**. The user checks by hand that neither needs sign-in or other dependencies before implementation. |
| G2 | Sample location | **One global `SAMPLES_DIR`**, which the user points at the current host's sample. No per-host key. Plan step 5.2.5 is dropped. |
| G3 | `.addin` handling | **Conditional.** Unpack `.addin` files as raw evidence only if the installer is not a `.bundle` with `PackageContents.xml`. Store Revit plug-ins normally are bundles, which the reader already handles. |
| G4 | Unsigned-add-in prompt | **Navigation guidance only**: Agent 2 clicks **Load Once**, because "Always Load" leaves lasting trust that UNIN-000 would flag. It is recorded as `load_prompt_seen` and as a report observation. |
| G4b | Verdict effect | Not a FAIL by itself. A signing check written by Agent 1 can FAIL on its own without blocking anything: LOAD-000 depends only on INST tests that observe `install_exit_code` (`agent1.py:179`). |
| G5 | LOAD-000 new document | **No code change.** The navigation file describes New → Project with the default template. The `new_document` regex is set after probing. |
| — | Sign-in or licence window during a run | Already covered by `host-interaction.md` §3–4 (class 3, never; stop the LOAD tests). A trial "days left" notice is information. |
| G6 | Genericity tests | Remove `revit` from the `app_words` list in `test_skills.py:125` and add `tiny tools\|archilizer\|renumber`. Keep `:93` strict. Add the Revit files to `EXPECTED` and add a `host_navigation("revit")` check. |
| G7 | `install_root()` | **Conditional, together with G3.** Only for a bare-`.addin` install: keep the file's parent folder, so a leftover `Addins\2027\x.addin` is within UNIN-000's `DEPTH = 2`. |
| G8 | `load_on_startup` rename | **No change.** |
| G9 | Inputs | `inputs/tiny-tools/`: the installer, `Description.txt` (written by the user) and `UserGuide.html` (downloaded). |
| G10 | Docs | ADR-048 plus ARCHITECTURE D68 (§2.6, §1, §7 table, :361) written now. The probed values are added after install. |

## 10. Probe results (2026-10-21, Revit 2027.3 installed)

| Item | Observed | Profile value |
|---|---|---|
| Registry | `HKLM\SOFTWARE\Autodesk\Revit\2027\REVIT-05:0809`: `ProductName = Autodesk Revit 2027`, `InstallationLocation = C:\Program Files\Autodesk\Revit 2027\`. Two levels below the root, so it fits `find_install_dir`. Checked with `resolve()`, which returns `C:\Program Files\Autodesk\Revit 2027\Revit.exe`. | `registry_root: 'HKLM:\SOFTWARE\Autodesk\Revit'`, `value: InstallationLocation`, `match_value: ProductName`, `match: '^Autodesk Revit \d{4}$'`. The `$` excludes `Components\ProductName = Revit 2027`. |
| Start args | The Start-menu shortcut starts it with `/language ENG`. The install language is British English. | `args: [/language, ENG]` |
| Process | `Revit.exe` | `processes: [Revit.exe]` |
| Main window title | `Autodesk Revit 2027.3 - NOT FOR RESALE (NON COMMERCIAL) - [Home]` | `main_window: '^Autodesk Revit \d{4}'` |
| New document title | Not probed yet; it needs a project opened. Expected: `... - [Project1 - <view>]`. | `new_document: 'Project\d+'` (confirm on the first run) |
| Home screen | It is a WebView ("Cloud First Model Browser"). UI Automation sees **no content** inside it, only the window, the title text, the status bar "Ready" and the system buttons. | Navigation: the Home screen is **Screenshot only**. Use **Ctrl+O**, which opens the Open dialog, instead of clicking Home tiles. |
| Opening the sample | `Revit.exe /language ENG <copy>.rvt` opened it in about 32 s. Title: `… - [sample.rvt - Sheet: G000 - Cover]`. A Win32 **"Unresolved References"** dialog appeared (5 missing links), with the choices "Open Manage Links…" and "**Ignore and continue opening the project**" as command-link `Pane`s. The name tools did not find them. | Navigation: choose Ignore, by Screenshot coordinates. |
| Ribbon | WPF ribbon, **visible to UI Automation**. Tab headers are `Button` elements (`Architecture`, …, `Add-Ins`, `Archilizer`, `Modify`). Only the active tab's panels and buttons are in the tree. Button names carry a **line break** (`Align⏎Views`, `Duplicate⏎Views`, `Duplicate⏎Sheets`, `Sheets⏎from Views`, `Bulk⏎Rename`, `Settings`), on panel "Views and Sheets". `click_ui("Archilizer", "Button")` worked (11.8 s). | ADR-049: whitespace-insensitive matching. |
| Project Browser | A **web view** (`Document "Project Browser"`). Rows are `ListItem`s, and only the visible rows are exposed. Filter buttons `All`, `Views`, `Legends`, `Schedules`, `Sheets`, `Families`, `Groups`, `Links`, and an `Edit "Search"` box. Finding it took 16 s. | ADR-049: 30 s limit. Navigation: filter or search first. |
| Security dialog | Did **not** appear. The user's manual test had already stored trust (`HKCU\Software\Autodesk\Revit\Autodesk Revit 2027\CodeSigning`). | The navigation file still covers "Load Once". |
| Name-tool timing | Each search over Revit's tree took 12–26 s (15 s limit). Searches for ribbon labels with a space failed. | Fixed by ADR-049. |
| Samples | Installed locally in `C:\Program Files\Autodesk\Revit 2027\Samples\` (registry `RCL\RVT_S_SAMPLES`): Snowdon Towers (Architectural, Structural, HVAC, …), Pacific Continental Residence, families. **No `rac_basic_sample_project.rvt`.** | `SAMPLES_DIR=C:\Program Files\Autodesk\Revit 2027\Samples\Snowdon Towers Sample Architectural.rvt` |
| Add-in folders | No `ApplicationPlugins` or `Addins\2027` folder yet, so nothing is installed. | ENV-000 starts clean. |

**Tiny Tools MSI** (`ArchilizerTinyTools.msi`, v2.0.1, Archilizer, ProductCode `{FF6100E2-7E6F-4530-9F58-7FE6A2D41AB2}`):
- **Per user.** All files go to `%AppData%\Autodesk\ApplicationPlugins\Archilizer_Bulk.bundle\`, with a `PackageContents.xml` and `Content\2024|2026|2027\windows\Archilizer_Bulk.addin`.
- `install_roots = ['%AppData%\Autodesk\ApplicationPlugins']`, the same as Plant 3D. No registry rows.
- **G3 and G7 are not needed** (bundle install). No change to `static_read.py` or `install_root()`.
- The MSI carries `Content\Tiny Tools _ Autodesk App Store.html`, which becomes embedded document `I1` automatically.
- Custom actions `LaunchEmail` and `LaunchDocHTML` (type 2) open the e-mail and the doc page from the UI sequence. A silent install (`/qn`) skips them.

**Built (2026-10-22):**
- `skills/hosts/revit.md`, `navigation/revit-navigation.md` and `navigation/revit-navigation-steps.md`;
- the ADR-049 change in `execute/ui_find.py` and `skills/execute/ui-find.md`;
- Revit coverage in `test_skills.py`, and a line-break test in `test_ui_find.py`.

All 257 tests pass. A dry run of intake and static read on `inputs/tiny-tools` gives D1, D2, I1 and U1, `Platform=Revit R2022–R2027`, and the install root `%AppData%\Autodesk\ApplicationPlugins`. Both hosts resolve to their executable.

**Run 20261022-101233 (stopped by hand, 2026-10-22):** ENV and INST passed. At LOAD-000, `WaitFor "Autodesk Revit"` matched the splash screen (title `Autodesk Revit 2027.3`). Agent 2's next model step then didn't return for over 3 minutes while the "Security - Unsigned Add-In" prompt waited. Fixed by ADR-050 (`wait_for_host`). Revit's `main_window` now requires ` - [`.

### Next (needs Revit 2027 installed)
1. Probe the machine: the registry locate block (check the shape `find_install_dir` expects), `Revit.exe` path and args, main and new-document window titles, and the UI Automation tree of the Home screen, ribbon, Project Browser, Open dialog and Security dialog.
2. Inspect the Tiny Tools installer: bundle or bare `.addin`. This decides G3 and G7.
3. Implement Phase 2 and Phase 3 as decided above.
