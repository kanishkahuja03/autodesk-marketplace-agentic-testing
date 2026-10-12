# Problem Statement: Automated Validation Pipeline for Autodesk Marketplace Plug-ins

## 1. Background

The Autodesk Marketplace (formerly the Autodesk App Store, `apps.autodesk.com`, which now redirects to `marketplace.autodesk.com`) has third-party plug-ins for Autodesk desktop products. Today, checking whether a plug-in installs correctly, loads in its host product, behaves as its description says and uninstalls cleanly is done by hand. That work is slow and the results vary from person to person.

We want an **agent pipeline** that takes a plug-in's **product description** and its **installer**, then does two things:

1. Works out what the plug-in is supposed to do.
2. Generates and runs test cases that check whether the plug-in is fine to install and use.

**Scope of the general product:** any app on the Autodesk Marketplace. That includes plug-ins for any host application (Autodesk or non-Autodesk) and standalone apps. The pipeline must be **generic**, not tied to one host. **AutoCAD Plant 3D is the first host** and the only one in the Monday POC test.

## 2. Problem

Given:
- a Marketplace plug-in's description text, and
- its installer (`.msi`, `.exe` or `.bundle`),

we have no automated way to:
1. turn the free-text description into a structured understanding of the plug-in: host product and versions, install footprint, commands, UI elements, and expected outputs;
2. derive repeatable test cases from that understanding;
3. run those test cases on a real Windows machine with the host product installed, and report pass or fail.

## 3. Proposed solution: a two-agent pipeline

```
 inputs/<plugin>/                Agent 1                         Agent 2
 ├─ *.txt/.pdf/.docx ──►  Analyst / Test Designer  ──►  Test Executor  ──►  report
 ├─ installer.*           • understanding.md            • runs test cases
 └─ metadata.json (opt)   • testcases.yaml              • pywinauto / Robot
                                                         • results.json
```

### Inputs (POC)
- No authentication and no Marketplace integration. Inputs are **copied by hand** into a local folder, one folder per plug-in. **The inputs are unstructured:** no fixed file names and no fixed content format.
  - The product description, pasted into a `.txt` file.
  - **Any number of third-party documents** from the publisher (user guide, readme, release notes and so on) in common formats: `.txt`, `.pdf`, `.docx`, `.html`.
  - The installer file, downloaded by hand. **Downloading needs an Autodesk ID sign-in, even for free apps.**
  - *Optional, for the future:* `metadata.json`, the Marketplace page data (supported versions, command list), if the store lets us get it.
- The pipeline sorts the files by type, extracts their text and lets Agent 1 cite any document by line (see `ARCHITECTURE.md` Stage 0).

### Agent 1: Analyst and Test Designer *(in scope for this POC)*
Reads the inputs and produces:

1. **`understanding.md`**, a working understanding of the plug-in:
   - its purpose and category (code plug-in or content pack);
   - the target host (Plant 3D, generic AutoCAD, or P&ID), with supported versions and release numbers (for example R25.1 for 2026);
   - the installer type and the install footprint it expects (`.bundle` folder, files in the content folder, Programs and Features entry);
   - the commands, ribbon tabs and dialogs it adds;
   - the outputs it should produce (files, catalog entries and so on);
   - assumptions, ambiguities, and anything the description does not say.
2. **`testcases.yaml`**, structured, machine-readable test cases that Agent 2 can run (draft schema in §6).

Rules for Agent 1:
- **Agent 1 only writes test cases. It does not run any test and does not inspect the target machine.** No test is run before Agent 1 either.
- Plain code may extract **facts from the inputs** and give them to Agent 1 (confirmed 2026-10-08):
  - the description and metadata;
  - the installer file's contents, read **without running it** (e.g. MSI tables, the plug-in manifest);
  - who the installer says it is signed by ("signed by X");
  - saved host knowledge from the host profile library.
- Anything that depends on the machine (install paths, the host's location and version) is written as a **placeholder** (e.g. `${CONTENT_DIR}`). Agent 2 fills it in.
- Test cases check **the plug-in**: its installation, how it is registered and loaded, and the behaviour its description claims. They must **not** test the host application's own APIs or features.
- Every test case must point back to the sentence or field in the input it came from.
- Anything that cannot be worked out from the inputs goes in the open-questions list. Agent 1 does not invent it.

### Agent 2: Test Executor *(minimum scope for this POC; fuller version later)*
- **The only place tests run.** Every check against the machine is a recorded test with evidence.
- First, **environment discovery**, which counts as the ENV tests: what is installed, where the host is and which version it is. For a known host, a saved host profile is used. For an unknown host, the **AI is in the loop**: it proposes what to look for, code does the checking, and a person approves the result once. Discovery then fills in Agent 1's placeholders.
- Runs the test cases from `testcases.yaml` on the local machine.
- **Pass/fail is always decided by code, never by the LLM.**
- Uses Python checks (file system, registry, `msiexec`) for environment and install/uninstall checks.
- Uses **pywinauto** (`uia` backend) or **Robot Framework** for UI checks, such as whether the ribbon tab is present and the command runs. Which one is used is still open (§10).
- Writes `results.json` (pass, fail or blocked per test case, with evidence such as logs and screenshots).

## 4. Scope for the Monday deadline

**In scope**
1. Choose the POC plug-in or plug-ins (§7).
2. Define the input folder layout and the test case schema.
3. Fact extraction from the inputs (description, metadata, installer static read), then Agent 1: `understanding.md` + `testcases.yaml` for the chosen plug-in(s).
4. Run a minimum set of test cases with Agent 2 for:
   - **Prerequisites:** Plant 3D is installed, its version is supported, and the required Plant 3D folders exist.
   - **Install:** the installer runs and finishes, and the expected footprint appears.
   - **Uninstall:** the uninstall runs, the footprint is removed, and nothing is left behind. The main path is the way a user uninstalls: **Control Panel → Programs and Features**, driven through the UI. A silent `msiexec /x` uninstall is the second path.

**Out of scope for now**
- Authentication, Marketplace download automation, publisher accounts.
- Paid plug-ins, or plug-ins with licence activation or online entitlement checks.
- **Running** tests on hosts other than Plant 3D, including non-Autodesk hosts. The design stays generic, so they can be added later.
- AI-in-the-loop discovery of new hosts (a stretch goal; Monday uses a hand-checked Plant 3D host profile).
- Testing the host application's own APIs.
- Deep functional testing of plug-in features beyond smoke level.
- CI, parallel runs, VM snapshots.

## 5. Test categories Agent 1 should generate

| Category | Example checks | Automation |
|---|---|---|
| **ENV** prerequisites (run first by Agent 2; this is the environment discovery) | The host is installed (for Plant 3D: registry `HKLM\SOFTWARE\Autodesk\AutoCAD\R26.0\ACAD-*:*`, `acad.exe` present); the installed version is in the plug-in's supported range; required folders exist (Plant 3D content folder, `ApplicationPlugins`) | Python, using the host profile (AI-assisted for unknown hosts) |
| **INST** install | The installer exits with code 0 (3010 means a restart is needed); a Programs and Features entry exists; the `.bundle` and `PackageContents.xml` exist and parse; `RuntimeRequirements` Platform and Series match the host; the expected files are in the content folder; the binaries are signed | Python |
| **LOAD** load and register | Plant 3D starts with no load errors; the ribbon tab or panel is present; the plug-in's commands are recognised (not "Unknown command") | pywinauto / Robot |
| **FUNC** smoke | One documented action works, such as an Info/About dialog opening, an export file being created, or a catalog opening in Spec Editor | pywinauto / Robot |
| **UNIN** uninstall | The uninstall finishes; the Programs and Features entry is gone; the `.bundle` or content files are gone from **every** candidate folder; any replaced stock files are restored; commands are unknown after a restart | Python + UI |

## 6. Draft test case schema (`testcases.yaml`)

```yaml
plugin:
  name: "<app name>"
  marketplace_app_id: "<guid>"
  host: { product: "Plant3D", versions: ["2027"], series: ["R26.0"] }
  installer: { file: "<name>.msi", type: "msi|exe|bundle", signer_claimed: "Kleen Software" }
required_env:                 # placeholders Agent 2 must fill in before running
  - HOST_EXE
  - CONTENT_DIR
  - PLUGIN_DIRS
testcases:
  - id: ENV-001
    category: ENV            # ENV | INST | LOAD | FUNC | UNIN
    title: "AutoCAD Plant 3D 2027 is installed"
    source: "metadata.json: supported 'AutoCAD Plant 3D' 2021-2027"   # where it came from
    preconditions: []
    steps:
      - action: host.detect               # actions are a fixed list Agent 2 knows
        params: { host_id: autocad-plant3d, version: "2027" }
    expected: "Host found; ${HOST_EXE} resolved"
    automation: python      # python | pywinauto | robot | manual
    priority: P1
  - id: INST-003
    category: INST
    title: "AWWA catalogs copied to the content folder"
    source: "description.md: 'copies AWWA Pipes and Fittings.pcat ...'"
    preconditions: [INST-001]
    steps:
      - action: sys.file_exists
        params: { path: '${CONTENT_DIR}\CPak AWWA\AWWA Pipes and Fittings.pcat' }
    expected: "File exists"
    automation: python
    priority: P1
```

The list of actions (`sys.file_exists`, `sys.registry_key_exists`, `sys.run_installer`, `host.detect`, `host.launch`, `ui.element_exists` and so on; full list in `ARCHITECTURE.md` §7) needs to be fixed so that Agent 1's output stays executable. Machine-specific values are always placeholders.

## 7. POC plug-in selection (research done 2026-10-08)

**Selection criteria:**
- Free.
- No licence activation, sign-in or online entitlement check.
- Plant 3D-specific.
- Supports current Plant 3D versions.
- A clear description with commands or UI to test.
- An install footprint that can be checked.

**Note on the Marketplace:** the store lists 785 apps under the `PLNT3D` product filter, and 222 of them are free. Most are generic AutoCAD apps that also list Plant 3D.

### Recommended shortlist

| Role | Plug-in (publisher) | Why |
|---|---|---|
| **Primary: code plug-in** | **P&ID Connector Exporter for Plant 3D** (Kleen Software). Free. Plant 3D 2021–2027. [Link](https://marketplace.autodesk.com/apps/d7287977-d0bc-467a-bddb-e825557b9d25) | Plant 3D only, no licensing, digitally signed, standard store installer that also uninstalls. Adds a **"P&ID Exporter"** ribbon tab with **Export** (JSON output we can check) and **Info** buttons. Covers ENV, INST, LOAD, FUNC and UNIN. Export needs an open P&ID project drawing; the Plant 3D sample project can be used. |
| **Secondary: content pack** | **AWWA Content Pack** (Autodesk). Free. Plant 3D 2024–2027. [Link](https://marketplace.autodesk.com/apps/57b9202e-549d-424b-be07-3fb6b23de0bd) | Simple, predictable footprint: copies `AWWA Pipes and Fittings.pcat` and `AWWA Valves.pcat` into the Plant 3D content folder under `CPak AWWA\`, and removes them when uninstalled through Control Panel. Covers the "required Plant 3D folder exists" and install/uninstall checks with little UI automation. |
| *Optional control* | **SmartIso** (Jan Grenov). Free. Generic AutoCAD, including Plant 3D. | Clear command list (`SmartIsoMake`, `SmartIsoDim` and others). Useful later to check that Agent 1 tells a generic AutoCAD plug-in apart from a Plant 3D-specific one. |

**Other free Plant 3D options:**
- Content packs: Georg Fischer, Victaulic, Grayloc/Techlok, IntegaDesign structural catalogs, Fire Fighting Sprinklers.
- Code plug-in: ISY Plant Review. Its commands can be smoke-tested, but real use needs PDMS data.

**Avoid for the POC:**
- Nozzle Content Pack and AS/NZ 3679: they **overwrite** stock `.acat` files.
- 3D Welds, Isolate, Codemill IFC Export, auxalia PlantTools: trials whose enforcement method is unknown.
- OrthoGen, Uno PlantExpress, ECE Worx, Nexal, DEXPI Data Bridge, PypeServer: they need activation, a subscription or a server.

## 8. Environment and known technical facts

| Item | Value | Confidence |
|---|---|---|
| Test machine | This machine. **AutoCAD Plant 3D 2027** (R26.0), licensed. Being installed as of 2026-10-08. | Confirmed by user |
| Shortlisted plug-ins on 2027 | The P&ID Connector Exporter and the AWWA Content Pack both list 2027 support on the Marketplace | Marketplace listing; verify by running |
| Plug-in folders scanned by the autoloader | `%ProgramFiles%\Autodesk\ApplicationPlugins`, `%ProgramData%\Autodesk\ApplicationPlugins`, `%AppData%\Autodesk\ApplicationPlugins` | Autodesk docs |
| ProgramData scanning in 2026+ | May be deprecated; check on the machine | Unverified |
| `PackageContents.xml` Platform value for Plant 3D | `Plant3D` (not `PLNT3D`, which is the Marketplace and launch product code) | Autodesk docs |
| Release numbers | 2024 = R24.3, 2025 = R25.0, 2026 = R25.1, 2027 = R26.0 | Third-party tables |
| Plant 3D registry product ID | `ACAD-x017:409` pattern (for example ACAD-9017 for 2026) | Inferred from older releases; **verify** |
| Plant 3D launch | `acad.exe /product PLNT3D` | **Verify** against the installed shortcut |
| Plant 3D shared content folder | `C:\AutoCAD Plant 3D 20xx Content\` by default; can be moved | Confirmed for older releases; verify |
| Marketplace MSIs honour `/qn` silent install | Unknown | **Verify** |
| UI automation | AutoCAD's ribbon is WPF hosted in MFC, so pywinauto needs the `uia` backend. The command line is a custom control, so input must be sent carefully. | Research |

## 9. Success criteria for the POC
1. For the chosen plug-in(s), Agent 1 produces an `understanding.md` that a reviewer agrees matches the Marketplace description, and a `testcases.yaml` that passes schema validation and covers the ENV, INST and UNIN categories (plus LOAD and FUNC for the code plug-in).
2. The ENV, INST and UNIN test cases run on this machine with Plant 3D installed and give correct pass/fail results, including a negative check that runs before Plant 3D is installed or after the plug-in is uninstalled.
3. Results are saved in a structured form with evidence.

## 10. Decisions and open questions (updated 2026-10-08)

| # | Topic | Status |
|---|---|---|
| 1 | **LLM provider** | Leaning towards **Google Gemini**, using free API keys. **No local LLMs.** Not final. The LLM layer must be easy to swap (see `ARCHITECTURE.md`). |
| 2 | **Plant 3D version** | **2027 (R26.0)**, being installed on this machine. |
| 3 | **Plant 3D licence** | Licensed. |
| 4 | **Agent 2 tooling** | Open. Pros and cons of pywinauto and Robot Framework are in `ARCHITECTURE.md`; the team decides after reading them. |
| 5 | **Uninstall method** | Both. **The main path is Control Panel → Programs and Features**, the way a user uninstalls. Silent `msiexec /x` is the second path. |
| 6 | **Clean state between runs** | Open. This means putting the machine back to how it was before a test run (see `ARCHITECTURE.md` §7). For the POC: scripted cleanup plus a file and registry snapshot comparison. VM snapshots come later. |
| 7 | **Installers and store details** | Kept in a local folder (`inputs/<plugin>/`) for now and downloaded by hand. This will be revisited later. |
| 8 | **Negative and edge cases** | Not at this stage. Planned for later. |
| 9 | **Agent 1 only designs; Agent 2 only runs tests** | Decided. No test runs and no machine inspection before or in Agent 1. Code may give Agent 1 facts from the inputs, including a static read of the installer and the claimed signer. |
| 10 | **Host profile library** | Decided. Agent 1 may read saved host knowledge. Real paths are only resolved by Agent 2. |
| 11 | **LLM in Agent 2** (host discovery, finding UI elements) | Accepted for now; may change later. Pass/fail is always decided by code. |
| 12 | **Generic hosts** | Decided. The design covers any host, including non-Autodesk hosts. Only Plant 3D is tested for Monday. |
