# Architecture & Approach: Marketplace Plug-in Validation Agents

> Companion to [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md). This is an exploration draft for the team to discuss.
> Status: **v0.3, 2026-10-09**. v0.3 adds unstructured multi-file inputs (§3, Stage 0) and the reasons for choosing YAML (§3.1). For agent basics, see [`AGENT_FUNDAMENTALS.md`](AGENT_FUNDAMENTALS.md). v0.2 changes: Agent 1 now only designs tests and Agent 2 only runs them (§1, §2), environment discovery has moved into Agent 2, and the design is generic for any host. Items marked *(verify)* still need checking on the Plant 3D 2027 machine.

---

## 1. Design principles

1. **Agent 1 designs the tests; Agent 2 runs them.** Nothing before Agent 1 or inside it runs a test or inspects the target machine. Agent 1 works **only from the inputs**: the description, the metadata and the installer file. Every check against the machine is a recorded test run by Agent 2.
2. **Automate everything that can be repeated.** A human only drops the inputs into a folder and, optionally, approves the test plan before it runs.
3. **Code does what can be decided; the LLM does what needs judgement.** The LLM reads descriptions, designs tests and helps discover unfamiliar hosts. Code installs software, reads the registry and **decides pass or fail**.
4. **The LLM works from facts.** Plain code pulls hard facts out of the inputs (the installer contents, who signed it, the metadata) and gives them to Agent 1 along with the description.
5. **The LLM only produces data.** Agent 1 outputs YAML. Agent 2 only runs actions from a fixed **action catalog**. The LLM never writes or runs shell commands or code.
6. **Generic by design.** Plant 3D is only the first host. Anything specific to one host lives in **host profiles** (data files), not in code. Non-Autodesk hosts are in scope for the design, but not for the Monday test.
7. **The LLM can be swapped.** Gemini for now; every LLM call goes through one small interface.
8. **Every result carries evidence.** Logs, screenshots, before/after diffs, and a link back to the input sentence the test came from.

### What is allowed where (agreed 2026-10-08)

| Activity | Before or in Agent 1 | Only in Agent 2 |
|---|---|---|
| Parse the description and `metadata.json` | ✅ | |
| Read the installer file **without running it** (MSI tables, embedded manifest, file list) | ✅ (confirmed) | |
| Read who the installer claims is the signer ("signed by X") as a fact | ✅ (confirmed) | |
| Read the **host profile library** (saved knowledge about hosts) | ✅ (confirmed) | |
| Check whether the signature is **valid** (a verdict) | | ✅ INST test |
| Inspect the machine: installed programs, host location and version, folders | | ✅ ENV tests |
| Install, launch, check the UI, uninstall | | ✅ |
| Use an LLM to discover a host or find UI elements | | ✅ (accepted for now; verdicts stay with code; may be revisited) |

---

## 2. High-level architecture

```
                         ┌──────────────────────────────────────────────────────────────┐
 inputs/<plugin>/        │                     ORCHESTRATOR (Python CLI)                │
 ├─ *.txt / .pdf /  ───► │                                                              │
 │  .docx / .html …      │  ── DESIGN SIDE (no machine access, no tests) ────────────── │
 ├─ installer.msi/exe    │  Stage 0  Intake: classify files, extract text,    (code)    │
 └─ metadata.json (opt.) │           hashes, read signer                                │
                         │  Stage 1  Installer static read (no install)       (code)    │
 host_profiles/*.yaml ─► │  Stage 2  Host knowledge lookup (library file)     (code)    │
                         │                                                              │
                         │  ┌──────────── AGENT 1: Analyst & Test Designer (LLM) ─────┐ │
                         │  │ 1a Extract facts → plugin_profile.json (incl. host)     │ │
                         │  │ 1b Write understanding.md                               │ │
                         │  │ 1c Design testcases.yaml (catalog actions, ${VARS})     │ │
                         │  │ 1d Self-check: schema + citation + coverage → fix loop  │ │
                         │  └─────────────────────────────────────────────────────────┘ │
                         │                                                              │
                         │  Stage 3  Review gate (optional human approval)              │
                         │                                                              │
                         │  ── EXECUTION SIDE (the only place tests run) ────────────── │
                         │  ┌──────────── AGENT 2: Test Executor ─────────────────────┐ │
                         │  │ E1 Environment discovery = ENV tests                    │ │
                         │  │    inventory → host resolution (profile or AI-in-loop)  │ │
                         │  │    → env.json (fills ${HOST_EXE}, ${CONTENT_DIR} …)     │ │
                         │  │ E2 Run INST / LOAD / FUNC / UNIN via action catalog     │ │
                         │  │    sys.* snap.* host.* ui.* cp.*   (pass/fail by code)  │ │
                         │  │ LLM assist: host discovery, UI locators, failure triage │ │
                         │  └─────────────────────────────────────────────────────────┘ │
                         │                                                              │
                         │  Stage 4  Report: results.json + report.html + evidence/     │
                         └──────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                runs/<plugin>/<timestamp>/   (all artefacts)
```

A benefit of this split: the design side can run on **any machine**, even one without the host installed. Only the execution side needs the test machine.

---

## 3. Design side: Stages 0–2 and Agent 1

### Stage 0: Intake (code)

**The inputs are unstructured.** For each plug-in, a person drops whatever they have into one folder, with no required names and no required format:
- the product description pasted into a `.txt` file;
- any number of **third-party documents** (user guide, readme, release notes, installation guide…) from the publisher, Kleen Software in our first case;
- the installer;
- *optionally, in future:* `metadata.json` from the Marketplace.

```
inputs/pid-connector-exporter/
├─ description.txt                    # pasted from the store page
├─ PID_Exporter_User_Guide.pdf        # third-party doc (any name)
├─ ReleaseNotes.docx                  # third-party doc (any name)
├─ PIDConnectorExporter.msi           # installer
└─ metadata.json                      # optional / future
```

What Stage 0 does:
1. **Classifies each file by type, not by name:**
   - installer: `.msi`, `.exe`, `.zip` that contains a `.bundle`;
   - document: `.txt`, `.md`, `.pdf`, `.docx`, `.html`/`.htm`, `.rtf`;
   - metadata: `metadata.json`.

   Unknown types are listed with a warning and skipped. If there is no installer, or more than one, the run stops with a clear message.
2. **Extracts plain text** from every document:
   - `.pdf` with `pypdf` or `pdfplumber`;
   - `.docx` with `python-docx`;
   - `.html` with `beautifulsoup4`.

   Each document gets an ID (`D1`, `D2`, …) and **numbered lines**, so Agent 1 can cite *"D2, line 41"* and the self-check can confirm the quote is really there. Text inside images (e.g. screenshots in a PDF) is not read for now.
3. **Makes a manifest** (`intake_manifest.json`): every file, its type, its SHA-256 hash, its size, and how many characters were extracted. If extraction finds very little text, the manifest warns that the document may be scanned images.
4. Reads the installer's **signer name** and records it as a fact ("signed by Kleen Software"). Whether the signature is *valid* is checked later, in an Agent 2 INST test.
5. **Size budget.** All extracted text is sent to Agent 1 together while it fits the LLM's per-request token budget. The free Gemini tier limits tokens per minute, so the budget is set in configuration. Larger document sets would need to be split into chunks and filtered for relevant parts; that comes later.


#### Input: `metadata.json` (optional, for the future)
This is the app's **Marketplace listing as structured data**. The Marketplace website loads every app page from JSON that can be read without signing in. It holds the same information as the page, already split into named fields.

| Field | Example (P&ID Exporter) | What we use it for |
|---|---|---|
| `appId`, name, publisher, app version | `d7287977-…`, Kleen Software | Ties each run to the exact app and version tested |
| Price plan (`FREE`, `TRIAL_30_DAYS`, …) | FREE | Leave out trial and paid apps |
| Supported products and versions (`productInfos`) | Plant 3D 2021–2027 | **Main hint for which host the plug-in targets** (Agent 1 step 1a) and the basis for ENV test cases |
| `commands` list | command names + descriptions | LOAD test cases (command recognised after install, unknown after uninstall) |
| Install / uninstall instructions | "Run installer again and choose Uninstall" | How the INST/UNIN test cases should install and uninstall |
| Trial text, certifications, signed flag | "Digitally signed" | Expected results for licensing and signature test cases |

Why it matters:
1. **Less guessing.** Commands and versions come as clean lists, not marketing text.
2. **Traceability.** The run records which app and version were tested.

Caveat: this is the website's **internal** data, not an official API, so it can change without notice. The pipeline must work without it. For the POC, save it by hand or write a minimal version yourself:

```json
{
  "app_id": "d7287977-d0bc-467a-bddb-e825557b9d25",
  "name": "P&ID Connector Exporter for Plant 3D",
  "publisher": "Kleen Software",
  "price": "FREE",
  "supported": { "AutoCAD Plant 3D": ["2021", "2022", "2023", "2024", "2025", "2026", "2027"] },
  "commands": [],
  "install_notes": "...",
  "uninstall_notes": "..."
}
```

### Stage 1: Installer static read (code, nothing is installed or run)
Purpose: give Agent 1 **facts from the installer file itself** instead of guesses.

| Installer type | What we extract | How |
|---|---|---|
| `.msi` | ProductCode, UpgradeCode, ProductName, Version, Manufacturer, ALLUSERS (per-machine or per-user), the **File and Directory tables** (where it *intends* to install), custom actions | Windows Installer COM (`WindowsInstaller.Installer`) through `pywin32`, or `lessmsi` |
| `.exe` | Installer technology (Inno, NSIS, InstallShield, WiX burn, Autodesk wrapper), embedded MSI if there is one, silent-install switches | Signature or string sniffing; 7-Zip extraction into a sandbox folder (untrusted data, never run from there) |
| `.bundle` / zip | `PackageContents.xml`: RuntimeRequirements (Platform, SeriesMin/Max), ComponentEntry (DLLs, load flags), **Commands** | XML parsing |

Output: `installer_facts.json`.

### Stage 2: Host knowledge lookup (code, reads a file only)
- Agent 1 step 1a names the target host and versions, for example "AutoCAD Plant 3D 2021–2027". Code then looks it up in the **host profile library** (`host_profiles/*.yaml`, see §5).
- **Profile found:** it goes to Agent 1 as **knowledge**: where plug-ins usually go, how the host is launched, what "ready" looks like. It contains **no machine-specific values**. Real paths are only resolved by Agent 2.
- **No profile** (a new host, possibly non-Autodesk): Agent 1 writes **discovery test cases** from general knowledge, for example "find where host X is installed and which version it is". They are marked `unverified`. Agent 2 runs them with AI in the loop (§4, E1) and proposes a new profile for a person to approve.
- **Standalone apps** (no host) use the minimal `host_id: none` profile. Only the Windows-level checks apply: installed, Start menu entry, app launches, uninstall.

### Agent 1: Analyst and Test Designer (LLM)
A fixed sequence of LLM calls, not a free-roaming agent, which keeps it predictable, cheap and easy to debug. **It has no access to the machine.**

| Step | Input | Output | Notes |
|---|---|---|---|
| **1a Extract** | all extracted documents (with line numbers), metadata if present, `installer_facts` | `plugin_profile.json` (Pydantic schema), including the **target host** | Structured output. Each field has a `source` quote and a `confidence`. Unknown fields stay `null` and are not guessed. Stage 2 (host knowledge lookup) runs right after this step. |
| **1b Understand** | profile + host knowledge | `understanding.md` | Fixed Markdown template. Lists anything the inputs don't say (open questions). |
| **1c Design tests** | profile + host knowledge + **action catalog** + test design rules | test cases as **schema-enforced JSON** from the LLM, validated by Pydantic, then saved as `testcases.yaml` (see §3.1) | Covers ENV, INST, LOAD, FUNC and UNIN. Uses catalog actions only. Uses **placeholders** (`${HOST_EXE}`, `${CONTENT_DIR}`, `${PLUGIN_DIRS}`) for anything machine-specific, and lists them under `required_env`. |
| **1d Self-check** | the YAML | pass, or a list of errors fed back for up to N retries | Code checks: schema validation, every action is in the catalog, every `source` quote **really appears** in the inputs (substring match, which catches invented claims), the required categories are covered, and every placeholder is listed in `required_env`. |

### 3.1 Why `testcases.yaml`? (decision record)

**What the output has to do:**
1. **Agent 2 runs it**, so it must be machine-readable with a strict structure.
2. **A person reviews it** at the review gate, so it must be easy to read and edit.
3. **It is checked automatically** (schema, catalog actions, source quotes).
4. **It is versioned** in git, so changes must show clearly in a diff.
5. **It doesn't depend on which executor we choose**, pywinauto or Robot.

| Format | Machine-readable | Easy for people to read and edit | Schema validation | Clean git diffs | Executor-neutral | Verdict |
|---|---|---|---|---|---|---|
| **YAML** | ✅ | ✅ Low noise, comments, multi-line text | ✅ Same data model as JSON, so the same JSON Schema and Pydantic models apply | ✅ | ✅ | **Chosen as the stored and reviewed format** |
| JSON | ✅ | ⚠️ Brackets and quotes everywhere; no comments | ✅ | ⚠️ | ✅ | **Used between the LLM and our code** (see below) |
| Robot `.robot` | ✅ Only by Robot | ✅ | ❌ No real schema; free-text keywords | ✅ | ❌ Locks us into Robot | Can be **generated from** the YAML later |
| Gherkin `.feature` | ⚠️ Needs separate code for each step | ✅ | ❌ | ✅ | ⚠️ | Too loose for parameters such as paths and registry keys |
| Excel / CSV | ⚠️ | ✅ | ❌ | ❌ Binary file / messy diffs | ✅ | Can be **exported** for managers if wanted |
| Markdown table | ❌ | ✅ | ❌ | ✅ | ✅ | Kept for the human summary in `understanding.md` |

**How it works in practice:**
1. Gemini's structured output can force valid JSON that matches a given schema, which avoids YAML-specific mistakes. **So the LLM returns JSON.**
2. Our code **validates** that JSON with Pydantic.
3. Our code **writes it out as YAML** for review and storage. It also keeps a `.json` copy for tools.

YAML and JSON hold exactly the same data; only the presentation differs.

**Known YAML pitfalls and how we avoid them:**
- **Indentation errors:** a person could make them when editing by hand, but the file is always re-validated before Agent 2 runs it.
- **Unexpected type conversion:** `NO` → `false`, `1.10` → `1.1`. We use a YAML 1.2 / safe loader and quote all strings when writing.
- **Windows backslash paths:** `C:\...` in double quotes can be read as escape sequences. We write such values as single-quoted strings.

**Short answer for reviewers:** *YAML is the readable, versionable, schema-checked form of the test plan. People can review it, and Agent 2 can run it. The LLM produces strict JSON, which we validate and convert to YAML. Because the plan is not tied to one executor, we can still generate Robot suites or Excel sheets from it.*

### Stage 3: Review gate
- On by default for the POC. A person skims `understanding.md` and `testcases.yaml` and approves (`--approve`), or the pipeline runs with `--auto`.
- This is the last point before anything touches the machine.

---

## 4. Execution side: Agent 2 (Test Executor)

### E1: Environment discovery (these are the ENV tests)
1. **Machine inventory** (code): installed programs from all Uninstall registry keys (name, version, publisher, install folder), OS version, admin rights, free disk space. Saved as evidence.
2. **Host resolution:**
   - **Profile exists and is verified:** code runs the profile's detection probes. No LLM is needed.
   - **No profile, or it is unverified (AI in the loop):** the LLM proposes a *probe plan* made of catalog actions (registry keys, folders, executables to look for), using the inventory and the discovery test cases. Code runs the probes, the LLM reads the results and refines the plan, up to N rounds. The result is saved as a **proposed host profile** for a person to approve once. After approval it goes into the library and later runs need no LLM.
3. **Write `env.json`:** fill in every `required_env` placeholder. If a placeholder can't be filled, the test cases that depend on it are marked `BLOCKED` and the reason is recorded.

### E2: Run the test plan
- **Runner (code):** runs INST → LOAD → FUNC → UNIN in order, filling placeholders from `env.json`. It applies the expected-result checks and saves evidence.
- **Statuses:** `PASS`, `FAIL`, `BLOCKED` (a prerequisite is missing), `NOT_APPLICABLE` (the test doesn't fit this machine), `ERROR` (a problem in the test harness itself).
- **LLM assist:**
  - *Host discovery* (E1.2).
  - *UI locators.* Give the LLM a dump of the UI Automation tree and ask "which element is the 'P&ID Exporter' ribbon tab?". The runner checks the locator it returns.
  - *Failure triage and report summary.*
  - **None of these decide pass or fail.**

### Stage 4: Report
- `results.json`, `report.html`, and an `evidence/` folder: screenshots, `msiexec /l*v` logs, snapshot diffs, inventory, and the text of the host's command line.
- Each result shows its status, its source quote and its evidence.

---

## 5. Host profiles (generic host support)

Anything specific to one host is data, not code. A profile says **how to find and drive** a host. It never stores the paths found on a particular machine; those go only in a run's `env.json`.

```yaml
host_id: autocad-plant3d
display_name: "AutoCAD Plant 3D"
vendor: Autodesk
status: verified            # verified | unverified (AI-proposed, waiting for approval)
versions:
  "2027":
    detect:   [{ action: sys.registry_key_exists, params: { hive: HKLM, path: 'SOFTWARE\Autodesk\AutoCAD\R26.0', match: 'ACAD-*017:*' } }]  # verify
    exe:      { from_registry: { path: '...', value: AcadLocation }, append: 'acad.exe' }
    launch:   '"${HOST_EXE}" /product PLNT3D /language en-US'                                           # verify
    plugin_dirs: ['%ProgramFiles%\Autodesk\ApplicationPlugins', '%AppData%\Autodesk\ApplicationPlugins']
    content_dir_default: 'C:\AutoCAD Plant 3D 2027 Content'                                             # verify
    ready_signal: { action: ui.element_exists, params: { window: 'Autodesk AutoCAD Plant 3D 2027*', locator: 'command line' } }
    known_popups: ['Start', 'File Loading - Security Concern']
notes_for_agent1: |
  AutoCAD-family plug-ins are .bundle folders with PackageContents.xml; Platform value for Plant 3D is "Plant3D";
  2027 = R26.0. Content packs copy .pcat/.acat files into the content folder.
```

**Why a library instead of asking the AI every time:**
- **Repeatable.** Once a profile is approved, host detection no longer depends on the LLM.
- **Cheaper.** Fewer LLM calls, which matters on the free tier.
- **Learns over time.** Each new host, Autodesk or not, is discovered once by the AI and approved once by a person.

---

## 6. Where we need an LLM and where we don't

| Task | Where | LLM? | Why |
|---|---|---|---|
| Parsing the inputs, static read of the installer, reading the signer | Stages 0–1 | No | Plain parsing |
| Reading the description into a structured profile | Agent 1 | **Yes** | Free text, no fixed format |
| Writing `understanding.md`, designing test cases | Agent 1 | **Yes** | Needs judgement |
| Checking the test plan (schema, quotes, coverage) | Agent 1 (1d) | No | Code checks this reliably |
| Discovering an unknown host | Agent 2 (E1) | **Yes**, AI in the loop | Every host is different; the AI proposes, code checks |
| Detecting a known host | Agent 2 (E1) | No | Runs the verified profile |
| Install, uninstall, registry and file checks, snapshot diff | Agent 2 | No | Must be repeatable and safe |
| Finding UI elements | Agent 2 | Optional | Fallback when fixed locators break |
| **Pass/fail verdict** | Agent 2 | **No** | Must be deterministic and auditable |
| Failure triage, report summary | Agent 2 / report | Optional | Has no effect on the verdict |

---

## 7. Action catalog (first version)

```
sys.registry_key_exists(hive, path, match?)        sys.registry_value_equals(...)
sys.file_exists(path)  sys.dir_exists(path)          sys.glob_count(pattern, op, n)
sys.xml_query(path, xpath, expected)               sys.signature_valid(path)
sys.run_installer(file, mode=silent|ui, args?)     sys.msiexec_uninstall(product_code)
sys.uninstall_entry_exists(name|product_code)      sys.process_running(name)
sys.inventory()                                    # installed programs, OS, rights
snap.take(label)   snap.diff(from, to) → added/removed/changed files & keys
host.detect(host_id, version)   host.launch(host_id, version, file?)   host.close(force?)
host.run_command(cmd)  host.command_line_contains(text)   host.wait_idle(timeout)
ui.element_exists(window, locator)  ui.click(window, locator)  ui.screenshot(label)
ui.dialog_present(title)  ui.dismiss_dialog(title, button)
cp.uninstall_via_programs_and_features(display_name)   # Control Panel uninstall, done through the UI
fs.file_created_since(path_pattern, t)  fs.json_valid(path)
```
`host.*` actions take their details from the host profile, so they work for any host that has one. Adding an action is a normal code change with tests. Agent 1 is given the catalog in its prompt.

---

## 8. Recommended tech stack

| Layer | Recommendation | Alternatives | Notes |
|---|---|---|---|
| Language | **Python 3.12** | — | Every tool we need (pywinauto, Robot, pywin32, google-genai) is Python |
| Orchestrator / CLI | **Typer** CLI plus plain Python stages | Prefect or Dagster (later) | A linear pipeline needs no workflow engine for the POC |
| Agent framework | **None for the POC.** Direct SDK calls behind an `LLMClient` interface, with Pydantic for structured output | **Google ADK** (Gemini-native), **LangGraph** (graphs, retries, human-in-the-loop), **PydanticAI** | Agent 2's host discovery loop is the first candidate for a framework |
| LLM | **Gemini Flash-tier** through the `google-genai` SDK, JSON-schema output | Gemini Pro (paid), Claude, OpenAI, Azure OpenAI | See §8.1. No local LLMs. |
| Schemas | **Pydantic v2** (installer facts, profile, host profile, test cases, env, results) | — | One source of truth |
| Document text extraction | `pypdf` or `pdfplumber` (PDF), `python-docx` (Word), `beautifulsoup4` (HTML) | PyMuPDF (fast, but **AGPL licence**, so avoid it in a company product unless legal approves) | Stage 0 |
| YAML | `ruamel.yaml` (YAML 1.2, keeps comments and order) | PyYAML (`safe_load`) | Avoids YAML 1.1 pitfalls such as `NO` being read as `false` |
| Prompts | Versioned Jinja2 files in `prompts/` | — | Prompt version is recorded per run |
| Windows access | `pywin32` (registry, COM, MSI), `subprocess` (`msiexec`), PowerShell where simpler | `wmi` (avoid `Win32_Product`, which triggers MSI repairs) | |
| UI automation | **pywinauto (`uia`)** or **Robot Framework**; see §10 | FlaUI (.NET) | Decision pending |
| Host driving | UI automation, plus the host's own automation interface where the host profile defines one (for AutoCAD: COM `SendCommand`, *verify ProgID for 2027*) | Typing keystrokes | Only used to *drive* the host, never to test the host's API (agreed scope) |
| Snapshots | Our own code: hash the files in watched folders and export watched registry keys before and after | Procmon (later) | Watched folders come from the host profile plus the standard Program Files, ProgramData, AppData and Uninstall keys |
| Reporting | Jinja2 → `report.html`, JSON results | Allure, Robot `log.html` | |
| Tooling | `uv`, `ruff`, `pytest`, `pre-commit`, git | | |
| UI inspection | **Accessibility Insights for Windows** / `inspect.exe` | pywinauto `print_control_identifiers()` | For finding locators |

### 8.1 Gemini free tier: points to know
- **Model availability changes.** Reports from 2026 say the free tier is now **Flash and Flash-Lite only**. Check the current models and limits in **Google AI Studio**; do not hard-code them.
- **Rate limits are low:** roughly 10–15 requests per minute and a few hundred to about 1,500 per day, depending on the model, per project. Agent 1 needs about 4–8 calls per plug-in; Agent 2 needs a few more only when it is discovering a host or finding UI elements. Add retry with backoff for HTTP 429.
- **Data use:** free-tier prompts may be used by Google; check the current terms. Marketplace data is public, so that is acceptable. **Never send internal or customer data.** Note that Agent 2's machine inventory lists the software on the test machine, so only send the LLM the parts it needs.
- **Structured output:** JSON schema generated from Pydantic, and always re-validated on our side.
- **Recording:** model name, temperature (0–0.2) and prompt version go into every run.

---

## 9. Clean state between runs

**What it means:** after a run, the machine may still have leftovers, such as plug-in files, registry entries or a changed host profile. The next run then starts "dirty" and can give false results.

| Option | Effort | Reliability | When |
|---|---|---|---|
| **A. Scripted cleanup + snapshot check:** before a run, check the snapshot has no trace of the plug-in; afterwards, remove anything the diff shows was added | Low | Medium | **POC** |
| B. Reset the host's user profile | Low | Medium | POC, if UI or profile state causes problems |
| C. **Hyper-V VM checkpoints**: restore a clean host checkpoint for each plug-in | Medium (Windows 11 Pro has Hyper-V; the host must be licensed inside the VM) | High | Next phase |
| D. Disposable cloud VMs | High | High | Scale-up |

---

## 10. Agent 2 UI tooling: pywinauto or Robot Framework

| | **pywinauto** (`uia` backend) | **Robot Framework** (+ `robotframework-flaui` or `RPA.Windows`) |
|---|---|---|
| **What it is** | Python library | Keyword-driven test framework (Python-based); UI automation comes from libraries |
| **Fit with our pipeline** | ✅ Direct: the runner calls Python functions | ⚠️ Indirect: we generate `.robot` files or call Robot's API, an extra translation layer |
| **Fit with LLM-generated tests** | ✅ YAML → Python action catalog | ✅ Keywords read like plain English, so the LLM could write them directly (but that is harder to restrict and check) |
| **Reports** | ❌ Build our own | ✅ `log.html` and `report.html` with screenshots, out of the box |
| **WPF/modern UI (e.g. AutoCAD ribbon)** | ✅ `uia` backend sees it | ✅ FlaUI (UIA3) sees it, often more robust on WPF |
| **Debugging** | ✅ Normal Python debugger | ⚠️ Keyword stack traces are harder to follow |
| **Maintenance** | ⚠️ Slow releases: 0.6.9 (Jan 2025) came after 0.6.8 (2019). Stable, but slow | ✅ Core is active; library quality varies (FlaUI has a known Python.NET crash workaround: `PYTHONMALLOC=malloc`) |
| **Learning curve** | Low for Python developers | Medium (new syntax and conventions) |
| **Non-developers reading tests** | ❌ | ✅ |
| **Dependencies** | Python + pywin32/comtypes | Robot + library + (for FlaUI) .NET via Python.NET |
| **Time to build the POC** | ✅ Faster | ⚠️ Slower to start |

**Suggestion:** use pywinauto for the POC, behind the `ui.*` interface. Because Agent 1 only writes YAML actions, a Robot backend can be added later, or `.robot` suites generated from the YAML, without touching Agent 1. Hybrid option if the team wants Robot's reports now: generate `.robot` files from `testcases.yaml` and write the keywords in Python on top of pywinauto.

---

## 11. Challenges and risks

| # | Challenge | Impact | Mitigation |
|---|---|---|---|
| 1 | **UAC prompts.** Installers and Control Panel uninstalls ask for admin rights. The UAC dialog runs on the secure desktop, where **UI automation cannot click it**. | Blocks automation | Run the orchestrator **as administrator**. *(Verify)* whether a Programs and Features uninstall started from an elevated session still prompts. If it does: a test VM with a changed UAC policy (IT decision), or keep that step semi-manual for now. |
| 2 | **Host startup:** slow (Plant 3D 30–90 s), Start tab, pop-ups, licence or sign-in dialogs | Flaky LOAD/FUNC tests | `host.wait_idle` with timeouts; handlers for the pop-ups listed in the profile; `BLOCKED`, not `FAIL`, when the host itself can't start |
| 3 | **Sign-in session expires** (Autodesk named-user licence) | All host tests blocked | ENV test detects a login window → `BLOCKED`; manual re-login runbook |
| 4 | **Ribbon/UI automation:** WPF inside MFC; controls created lazily, often unnamed | Brittle locators | Locators found with Accessibility Insights; activate the tab first; use the host's command interface; LLM locator search as a fallback |
| 5 | **Command line input** in AutoCAD-family hosts is a custom control | Wrong command runs | Send Esc Esc first; prefer COM `SendCommand`; check the command echo |
| 6 | **SECURELOAD / trusted locations** dialog for untrusted plug-ins | Test hangs | Detect the dialog, record it as a finding, choose "Load" only in test runs |
| 7 | **2027 = R26.0 is new:** .NET changes; the ProgramData plug-in folder may no longer be scanned | Plug-in may not load even though the store claims support | This is exactly what we want to catch. The snapshot shows where it installed, and LOAD tests confirm whether it loads |
| 8 | **Store installers:** `/qn` may not work, EULA dialogs, per-user installs into `%APPDATA%` | Hard to automate | Default to UI install with a dialog handler; silent install as a separate test; the snapshot diff finds the real location |
| 9 | **LLM invents facts** | Wrong tests | Facts from the inputs (Stages 0–1), source quotes checked by substring match, action whitelist, `null` instead of guessing, review gate |
| 10 | **Agent 1 can't see the machine,** so some tests won't fit it | Not-applicable tests | Placeholders plus `required_env`; Agent 2 marks `BLOCKED` or `NOT_APPLICABLE` with a reason. Later: feed Agent 2's findings back to Agent 1 to revise the plan |
| 11 | **AI-proposed host profiles may be wrong** (new hosts) | Wrong ENV results | Profiles stay `unverified` until a person approves them; tests that depend on an unverified profile are flagged in the report |
| 12 | **Prompt injection:** descriptions are third-party text | Agent misbehaviour | Agent 1 has no tools; outputs are schema-checked data; Agent 2 runs catalog actions only; inputs are marked untrusted in prompts |
| 13 | **Untrusted installers** run on the machine | Security | Signature validity is the first INST test; use a dedicated test machine or VM later (this machine for now, risk accepted knowingly) |
| 14 | **Free LLM tier:** rate limits, model changes, data use | Failures, drift | Backoff; record model and prompt version; swappable `LLMClient`; send the minimum data |
| 15 | **Description quality varies** | Weak tests | Use `metadata.json`; Agent 1 lists gaps in `understanding.md` |
| 16 | **FUNC tests need data** (e.g. an open P&ID drawing) | Can't smoke-test | `test_assets/` with the sample project, declared as a precondition |
| 17 | **Non-determinism** | Hard to compare runs | Low temperature; store the YAML; an approved YAML becomes a "golden" plan that is re-run without the LLM |

---

## 12. What each agent needs, and team skills

### Agent capabilities
| Agent | Knowledge (prompt or context) | Tools / abilities | Guardrails |
|---|---|---|---|
| **Agent 1** | General Windows installer and plug-in knowledge; the matching **host profile** and its `notes_for_agent1`; test design rules; the action catalog | **None.** Data in, data out. No machine access | Structured output, `source` quotes, `null` instead of guessing, placeholders for machine values, self-check loop |
| **Agent 2** | Approved `testcases.yaml`, host profiles, `env.json` | Action catalog (sys, snap, host, ui, cp); AI-in-loop host discovery; evidence capture; timeouts; pop-up handler | Whitelisted actions only; pass/fail decided by code; every step has a timeout; never runs anything taken from the description; stops on unexpected system-wide changes |
| *(Later)* Triage agent | Results, logs, diffs | Read-only | Advisory only |

### Team skills
| Area | Needed for |
|---|---|
| Python (typing, Pydantic, subprocess, packaging) | Everything |
| Windows internals: registry, MSI/msiexec, UAC, Authenticode, permissions | Stages 0–1, Agent 2 ENV/INST/UNIN |
| Host-specific knowledge, AutoCAD/Plant 3D first: bundles, autoloader, SECURELOAD, COM, projects and content folders | Host profiles, LOAD/FUNC tests |
| UI automation (UIA, pywinauto/Robot, Accessibility Insights) | Agent 2 UI actions, Control Panel uninstall |
| LLM engineering: prompts, structured output, evaluation | Agent 1, Agent 2 host discovery |
| Test design (QA) | Test categories, review gate, golden plans |

---

## 13. Proposed repository layout

```
AutodeskMarketplaceAgent/
├─ PROBLEM_STATEMENT.md
├─ ARCHITECTURE.md
├─ inputs/                       # one folder per plug-in (manually placed)
│  ├─ pid-connector-exporter/  {any .txt/.pdf/.docx docs, installer.*, metadata.json (optional)}
│  └─ awwa-content-pack/
├─ host_profiles/                # host knowledge (plant3d.yaml first; AI-proposed ones wait for approval)
├─ test_assets/                  # sample projects/drawings for FUNC tests
├─ src/mpagent/
│  ├─ cli.py                     # typer: design | review | run | report | all
│  ├─ models/                    # pydantic: installer_facts, plugin_profile, host_profile, testcase, env, result
│  ├─ design/                    # DESIGN SIDE (no machine access)
│  │  ├─ pipeline.py  intake.py  static_read.py  host_lookup.py  context.py
│  │  └─ agent1/                 # extract.py, understand.py, design.py, selfcheck.py
│  ├─ execute/                   # EXECUTION SIDE
│  │  ├─ agent2/                 # runner.py, env_discovery.py (inventory + host resolution)
│  │  └─ actions/                # sys.py, snap.py, host.py, ui.py, cp.py
│  ├─ llm/                       # LLMClient interface + gemini.py
│  └─ report/                    # html templates
├─ prompts/                      # versioned prompt templates
├─ schemas/                      # exported JSON schemas
├─ runs/<plugin>/<timestamp>/    # outputs + evidence (git-ignored)
├─ evals/                        # expected outputs for 2–3 plug-ins, to measure Agent 1 quality
└─ tests/                        # unit tests
```
Keeping `design/` and `execute/` separate in the code makes the boundary visible and easy to enforce. Nothing in `design/` imports from `execute/actions`.

---

## 14. Plan to Monday 2026-10-12

| When | Goal | Deliverables |
|---|---|---|
| **Thu 8 (pm)** | Docs; Plant 3D 2027 install finishes; download the 2 installers into `inputs/` | Both docs; inputs folders; check the *(verify)* items by hand and write `host_profiles/plant3d.yaml` |
| **Fri 9** | Design side | Pydantic models, intake, MSI static read, host lookup, Gemini client, Agent 1 steps 1a–1d → `understanding.md` + `testcases.yaml` for both plug-ins |
| **Mon 12** | Minimal Agent 2 + demo | E1 using the verified Plant 3D profile (AI discovery is a stretch goal); `sys.*` + `snap.*`; run **ENV, INST, UNIN** (msiexec, plus Control Panel UI if UAC allows); `results.json` + simple HTML report; LOAD/FUNC are stretch goals |

**Risks to the deadline:** Plant 3D install or sign-in, UAC (§11 #1), the installers' UI flow. Demo fallback: the design-side output plus ENV/INST/UNIN with silent install, with the Control Panel uninstall shown as the next step.

---

## 15. Later phases
1. AI-in-loop host discovery for new hosts, including non-Autodesk ones, with a profile approval workflow.
2. Full LOAD/FUNC UI tests, LLM-assisted locators, golden-plan re-runs.
3. Hyper-V checkpoint isolation; nightly batch runs.
4. Negative and edge cases (unsupported version, host missing, reinstall, upgrade).
5. Feedback loop: Agent 2 findings → Agent 1 revises the plan.
6. **Conflict detection across inputs.** Agent 1 compares the description, the third-party documents, the metadata and the installer contents, and reports disagreements in `understanding.md` instead of quietly picking one. Examples: a user guide for an older version naming different commands; the store saying 2027 while the manifest says `SeriesMax=R25.1`.
7. Marketplace integration (fetch metadata automatically; downloads still need an Autodesk ID).
8. Dashboard, trends, a triage agent.

## Sources
- Gemini free tier changes and limits (third-party summaries; confirm in AI Studio): [agentdeals.dev](https://agentdeals.dev/gemini-api-pricing-changes), [tinkerllm.com](https://tinkerllm.com/blog/gemini-api-free-tier-limits-rate-quotas/), [yingtu.ai](https://yingtu.ai/en/blog/google-gemini-api-free-tier)
- pywinauto releases: [PyPI](https://pypi.python.org/pypi/pywinauto), [piwheels](https://www.piwheels.org/project/pywinauto/)
- Autodesk plug-in packaging and autoloader: [Installing/Uninstalling Plug-ins](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Customization/files/GUID-5E50A846-C80B-4FFD-8DD3-C20B22098008.htm), [RuntimeRequirements](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Customization/files/GUID-1591CA01-EF87-48CD-952B-772FE26037F1.htm), [2025 RuntimeRequirements blog](https://blog.autodesk.io/autocad-2025-update-your-packagecontentsxml-with-runtimerequirements/)
- Marketplace data: [Plant 3D listing](https://marketplace.autodesk.com/search?productIds=PLNT3D), [public search API](https://developer.api.autodesk.com/ngappapi/public/search?productIds=PLNT3D)
