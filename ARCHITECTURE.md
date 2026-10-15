# Architecture V2: Generic Plug-in / App Validation Agents

> **Status:** v2.2, 2026-10-13. This is the build plan for the product. v2.1 added the grill-me decisions D16–D35 (one F5 run, preflight, cleanup, logging, guardrails, `record_observation`). **v2.2** records what the live runs of 2026-10-12/13 taught (D24, D26, D27, D30, D32, D33 updated; D36–D39 new): silent uninstall instead of the UI, read-only FileSystem, per-run guardrail rules, cleaned and capped tool results, app facts in Agent 2's input. First clean run: `20261013-152426` (3 PASS). **v2.3** (2026-10-13, branch `Dev-FunctionalTest`) adds the **LOAD** test level from the grill-me review of [`LOAD_TESTS_PLAN.md`](LOAD_TESTS_PLAN.md) (D7, D8, D9, D16, D29, D35 updated; D40–D57 new; D58–D67 new).
> **Supersedes:** [`ARCHITECTURE_old1.md`](ARCHITECTURE_old1.md) (v0.3). Where they disagree, **this document wins**, including over what is already in `CodeBase/`.
> **Inputs to this version:** [`ARCHITECTURE_COMPARISON.md`](ARCHITECTURE_COMPARISON.md) (ours vs `AppStore automation/`), [`AGENT_TOOLING_REVIEW.md`](AGENT_TOOLING_REVIEW.md) (tool lists, one by one), [`DESKTOP_UI_AUTOMATION_RESEARCH.md`](DESKTOP_UI_AUTOMATION_RESEARCH.md). Decision index: [`ADR.md`](ADR.md).

---

## 1. Context

Store QA for desktop plug-ins and apps is manual: install, check it registered, check it loads, check it uninstalls cleanly. That's slow and varies between reviewers.

We build a **generic** two-agent pipeline that takes an app's **documentation and installer** and returns a **report with code-decided verdicts and evidence**:
- **Agent 1** designs the tests.
- **Agent 2** runs them on a real Windows machine through a ready-made MCP server.

The goal **now** is a **demo POC with minimal development effort**, built from ready-made parts (OpenAI Agents SDK, Windows-MCP, existing libraries). Cost is not a concern. **The whole pipeline runs with one press of the Visual Studio Run button (F5).**

**Generic means:** nothing in the core is tied to Autodesk or any other vendor. Product-specific knowledge lives in **host notes** (Markdown skill files). AutoCAD Plant 3D 2027 is just the first host, and the **P&ID Connector Exporter** is the demo app.

---

## 2. Decisions (final)

### 2.1 Core (D1–D15)

| # | Topic | Decision |
|---|---|---|
| D1 | Scope | Generic: any Windows desktop plug-in or standalone app. Host specifics only in host notes. |
| D2 | LLM | **Enterprise OpenAI API** (platform.openai.com). Model name set in `.env`. Gemini removed. |
| D3 | Agent framework | **OpenAI Agents SDK** (`openai-agents`, Python) |
| D4 | Agent 1 | **Blind, single pass.** No tools, no machine access. Output: `understanding.md` + `testcases.yaml`. |
| D5 | Agent 2 | **One agent session for the whole plan**, driving the machine **only through Windows-MCP**. No action catalogue of our own. The single local exception is the reporting tool `record_observation` (D30). |
| D6 | UI interaction | **[Windows-MCP](https://github.com/CursorTouch/Windows-MCP)** (reads the accessibility tree, then clicks, types and takes screenshots) |
| D7 | Verdict | **Code** decides every **fact** (exit codes, registry, files, LOAD-000's host window and new document). **Claims about what the UI shows** are decided by an evidence-bound **LLM judge** (D58, 2026-10-14); Agent 2 never sets a status. |
| D8 | Demo test levels | **ENV, INST, LOAD, UNIN** (LOAD added in v2.3, D40–D52; FUNC later) |
| D9 | Human review gate | **One y/n review of the test cases** in the console after Agent 1 (D57, requested by the seniors 2026-10-14); otherwise fully automatic. |
| D10 | Doc extraction | **Keep the existing `intake.py`** (pypdf, python-docx, bs4) |
| D11 | Tracing | **Local only.** OpenAI tracing disabled. See D19 for the log files. |
| D12 | Machine | Dev machine, **run as administrator**. Risk accepted. VM later. |
| D13 | "Skills" | **SKILL.md-style Markdown files** loaded into each agent's instructions. OpenAI's hosted Skills API is not used (it runs in OpenAI's cloud). |
| D14 | Demo app | P&ID Connector Exporter (Kleen Software) on Plant 3D 2027 |
| D15 | Host lookup | **Done by Agent 1** (LLM reasoning over documents + installer facts), not by keyword code. Agent 1 picks a `host_id` from the available host notes, or `none` / `unknown`, and cites why. |

### 2.2 Run behaviour, safety and limits (D16–D35, from the grill-me session 2026-10-12)

| # | Topic | Decision |
|---|---|---|
| D16 | One Run button | **F5 always runs the full pipeline** (S0 → S1 → Agent 1 → test-case review → preflight → Agent 2 → verdicts → report → cleanup) into a **new** run folder. There are no sub-commands and no stop switches; the only question asked is the test-case review (D57). |
| D17 | Input selection | F5 tests **one input folder**, given as the only launch argument in `mpagent.pyproj` (`inputs/<app>`). To switch apps, change that value. |
| D18 | Agent 1 self-check failure | After 2 retries, the pipeline **stops before Agent 2**. The machine is untouched. It's reported **only in the logs**, with no separate report. |
| D19 | Logging | Per run: **`run.log`** (readable step status, also shown in the VS console, final `COMPLETED`/`STOPPED` line) and **`trace.jsonl`** (every LLM request/response and MCP call). `report.html` is written **only if Agent 2 ran**. |
| D20 | Preflight (code, just before Agent 2) | (1) The process is **elevated**. (2) Windows-MCP starts and exposes **exactly the 13 allowed tools**. (3) **ENV-000**: the plug-in is not installed yet (D23). Any failure → `STOPPED`, Agent 2 doesn't start. This runs after Agent 1, so Agent 1 stays blind. |
| D21 | Windows-MCP install | **Installed once beforehand** (pinned version, setup step in README, next to `uv sync`). F5 only starts it. |
| D22 | Plug-in already installed | INST and UNIN are **BLOCKED** and nothing is installed. Cleanup is manual. |
| D23 | ENV-000 | A **built-in test executed by code** in the preflight (registry lookup by ProductCode, or DisplayName as a fallback, from `installer_facts`). It's recorded in the results like any test, with `origin: built-in`. |
| D24 | Basic test coverage | **Agent 1 writes all other tests.** The **self-check enforces** that there's at least: one INST test observing the install exit code, one INST test observing that the Uninstall entry exists, and one UNIN test observing that the entry is gone. It also **rejects ENV tests that observe the app's installation keys** (`install_exit_code`, `uninstall_exit_code`, `uninstall_entry_exists`, `preinstalled_entry_exists`); ENV tests observe the machine or host (e.g. `host_installed`, `host_version`). *(Run 20261013-145150: a host test observed `uninstall_entry_exists` and failed falsely.)* |
| D25 | Gating | The only hard stops are the preflight checks (incl. ENV-000). All other dependencies are **per-test `preconditions`** written by Agent 1, applied **afterwards** by the verdict engine (→ BLOCKED). Agent 2 simply runs every test. |
| D26 | Install path | **Silent** `Start-Process -FilePath msiexec.exe -ArgumentList '/i',<msi>,'/qn','/norestart','/l*v',<run>\evidence\install.log -Wait`. There's no UI install and no automatic UI retry. Code **creates `evidence\` before Agent 2 starts** (otherwise msiexec can't open its log and aborts at once). Agent 2 runs the install **once** (enforced by D32) and takes `install_exit_code` from the log's `success or error status: N` line (via `Select-String`), never from PowerShell's own status code; no log or no result line → `null`. `-PassThru \| Select-Object -ExpandProperty ExitCode` is not used: inside Windows-MCP it always fails ("Process must exit before requested information can be determined"). *(Runs 20261012-191028, 20261013-131217.)* |
| D27 | Uninstall path | **Silent**, like the install: Agent 2 runs `msiexec /x <ProductCode> /qn /norestart /l*v <run>\evidence\uninstall.log` once, takes `uninstall_exit_code` from the log's `success or error status: N` line, then re-checks the Uninstall entry and the files. *(Changed 2026-10-13: the Programs and Features UI path made gpt-4o-mini scroll a 58-program list and select the wrong program — run 20261013-132121 had GlobalProtect selected with Uninstall clicked. The UI is kept for the host/plug-in screenshot test planned next.)* |
| D28 | Cleanup (code, `finally`) | Always runs at the end. If the ProductCode is known **and** the Uninstall entry still exists **and** UNIN didn't complete → `msiexec /x {ProductCode} /qn`, logged as `CLEANUP`. It **never changes a verdict**. Non-MSI → logs "manual cleanup needed". |
| D29 | Time limits | Agent 2: **150 turns**, **120 s per tool call**, **40 min total** (raised from 20 for LOAD; all in `.env`; waits capped by D50). If a limit is hit → the run is cancelled, missing tests become ERROR, cleanup runs, and it's logged. |
| D30 | Observations | Agent 2 reports **per test, as it goes**, through the local tool **`record_observation(test_id, observed, evidence, notes)`**. It appends to `observations.json` and never touches the machine. It **rejects evidence files that don't exist** in the run folder (Agent 2 must then record again with real files and only values it actually saw). An observation recorded with `executed: true` **can't be replaced** by a later `executed: false` one, and an identical repeat is answered "already recorded" instead of being saved again. The final agent output is only a short "done" plus the resolved env values. *(Run 20261013-125224: good results were overwritten by later failed attempts.)* |
| D31 | Screenshots | Our trace hook **saves every Windows-MCP screenshot** to `evidence/`, and code **attaches every screenshot taken since the previous `record_observation` call to the next one** automatically. Agent 2 lists only other evidence files (e.g. `evidence/install.log`). *Verified on Windows-MCP 0.8.6: `Screenshot` returns the PNG inline as base64 (plus a text block with the cursor position and coordinate scale) and saves no file, so our code must save it (`execute/windows_mcp.py: save_images`).* |
| D32 | PowerShell control | A code guardrail with an **allow-list of command starts**: `Start-Process -FilePath msiexec.exe` (with `-Wait`; a bare `msiexec` call returns before the install finishes), `Get-AuthenticodeSignature`, `Get-ItemProperty`, `Get-ChildItem`, `Test-Path`, `Select-String` (read-only search, e.g. the result line of a msiexec log), `Get-CimInstance Win32_OperatingSystem`, and the admin check. The command may not contain `;`, `\|\|`, `{ }` (except GUIDs), `$( )`, backticks, redirection or line breaks, nor `&` **outside quotes** (inside quotes it's text, e.g. `'P&ID Connector'`). Pipes may only go into output-shaping commands (`Select-Object`, `Format-List`, `Format-Table`, `Sort-Object`, `Measure-Object`, `Out-String`, `ConvertTo-Json`). Everything else is **rejected and logged**. |
| D33 | Registry / FileSystem control | Code guardrail: Registry **read/list only**. FileSystem is **read-only**: `read`, `list`, `search`, `info`; `write`, `copy`, `move` and `delete` are always rejected (Agent 2 reports through `record_observation`; evidence comes from the tools). A `read` without `limit` of a file over **50 KB** is rejected (use `Select-String` or `offset`/`limit`). Rejections are logged and the agent is told why. *(Run 20261013-145150: Agent 2 overwrote the real `install.log` with its own sentence; run 20261013-131217: a whole-file read of a 354 KB log overflowed the model's context.)* |
| D34 | Model | **One `OPENAI_MODEL`** for both agents (the strongest model available to the org). |
| D35 | Run result | The final `run.log` line is `COMPLETED: n PASS, n FAIL, n NEEDS_REVIEW, n BLOCKED, n ERROR — report: …` or `STOPPED: <reason>`. **Exit code:** 0 = completed (even with FAIL tests), 1 = stopped, 2 = unexpected crash. |

### 2.3 Lessons from live runs (D36–D39, 2026-10-13)

| # | Topic | Decision |
|---|---|---|
| D36 | Per-run guardrail rules | On top of D32/D33, a per-run `CallPolicy`: **a second `msiexec /i` is rejected** ("install only once, read the log"), and the **same tool call with the same arguments more than 3 times is rejected** (Snapshot, Screenshot, Wait and WaitFor are exempt). *(Run 20261013-125224: the installer ran twice and one FileSystem call was repeated 19 times.)* |
| D37 | Tool results sent to the model | Code cleans every Windows-MCP result before the model sees it: PowerShell **CLIXML progress noise is removed** and its error lines are decoded ("(PowerShell error output)"), and any text **over 20,000 characters is cut off** with a hint to use `Select-String` or `offset`/`limit`. The original result still goes to `trace.jsonl`. |
| D38 | App facts for Agent 2 | Code adds an **"App under test"** block to Agent 2's input: DisplayName, Publisher, Version, ProductCode, the three Uninstall registry paths with the ProductCode, the install roots expanded to real paths, and the machine's real folders (`%APPDATA%`, `%LOCALAPPDATA%`, `%USERPROFILE%`, `%ProgramFiles%`, …). Execution side only, so Agent 1 stays blind. *(Run 20261013-132121 guessed `C:\Users\Admin`, `C:\Users\User`.)* |
| D39 | Stopping a run | **Ctrl+C in the console** interrupts Agent 2, and the `finally` steps (cleanup, verdicts, report) still run; the log then ends without a COMPLETED/STOPPED line. The VS **Stop** button or closing the console kills the process, so cleanup can't run; the next run then stops at ENV-000 and prints the exact `msiexec /x {ProductCode} /qn` command to remove the leftover. |

### 2.4 LOAD tests (D40–D57, grill-me review of LOAD_TESTS_PLAN.md, 2026-10-13)

LOAD checks that the plug-in is **loaded by its host**: the host starts, opens a new document, and the app's entry point is visible. Details and reasoning: [`LOAD_TESTS_PLAN.md`](LOAD_TESTS_PLAN.md) §3 (L1–L18).

| # | Topic | Decision |
|---|---|---|
| D40 | What LOAD opens | The host plus its **default new document** (host-notes recipe). App-specific documents and projects are FUNC (later); Agent 1 records them as `entry_point.use_context`. |
| D41 | Who writes LOAD tests | Code adds the built-in **LOAD-000** "host ready with a new document" for hosts whose notes have `host_process`; it depends on the INST test(s) observing `install_exit_code`. Agent 1 writes **exactly one** test, **LOAD-001** "entry point visible" (cited, precondition `[LOAD-000]`), whenever the entry point is visible (`ribbon_tab`, `menu`, `toolbar`); the self-check requires it (run 20261013-172934). |
| D42 | Entry-point card | `summary.entry_point` (nullable): `kind`, `label`, `items` (only quoted names), `use_context`, `sources`. The self-check finds every name in the cited quotes. LOAD-001 checks the **label only**. *(LOAD-001 "label only" is superseded by D59 (claims judged; LOAD-002 for the items), 2026-10-14.)* |
| D43 | Host facts for code | Each host-notes file may have YAML front matter **`host_process`**: registry lookup of the install folder, executable, exact args, process names, main-window and new-document title regexes. Read by `mpagent/hostnotes.py`; no product names in code. |
| D44 | UI checks | New checks **`window_in_ui`** (a title matching a regex inside the host window) and **`seen_in_ui`** (an element named exactly the label inside the host window). Code parses only the **UI Tree** of the raw Snapshot texts attached to the observation, only under the host's main window; Agent 2's value is shown in the report but never decides. *(`seen_in_ui` is superseded by D58/D61; `window_in_ui` stays for LOAD-000, 2026-10-14.)* |
| D45 | NEEDS_REVIEW | New status: `seen_in_ui` label not found but a screenshot exists. Precedence BLOCKED → ERROR → FAIL → NEEDS_REVIEW → PASS. It isn't PASS, so dependents are BLOCKED. No host window or no Snapshot → ERROR; `window_in_ui` not seen → FAIL. |
| D46 | Raw Snapshot evidence | The recorder saves every Snapshot's **full** text as `evidence/<n>_Snapshot_ui.txt` (decoded if Windows-MCP returns a JSON list) and attaches it like screenshots. `record_observation` refuses an executed UI-checked test without a Snapshot since the previous record. |
| D47 | One session | Agent 2 stays **one session** (D5). A guardrail **rejects an uninstall `msiexec /x` while a host process runs**, so locked plug-in files can't spoil UNIN. UNIN never depends on LOAD. |
| D48 | Starting programs | The App tool may run only **`launch_executable` with the host's exact path and args** (path resolved by code, given in "Host program"); `launch` by name is rejected; `switch`/`resize` allowed. Without a host, App starts nothing. |
| D49 | Dialogs | **Replaced by D56** (2026-10-14). Was: a load/trust prompt for the app gets the one-time yes, and any other dialog stops LOAD; that blanket stop failed LOAD on a harmless plug-in notice (run 20261014-111858). |
| D50 | Closing and waiting | Agent 2 closes the host with **`Process kill` by name** (host processes allowed; kill by pid rejected); no saving, no graceful close. `Wait`/`WaitFor` are capped at tool timeout − 15 s (105 s). |
| D51 | Host already running | **Preflight stops** if a host process runs, so no user session is touched. `finally` kills the host **before cleanup**: kill host → cleanup → verdicts → report. |
| D52 | Host executable missing | If the registry lookup finds no executable, Agent 2 starts nothing and records LOAD as not executed. |
| D53 | Order enforced by code | The App tool can't start the host before `msiexec /i` has run in this run, and `record_observation` refuses an executed test observing `install_exit_code` when the installer never ran. *(Run 20261013-175002: Agent 2 skipped the install, started the host and recorded INST-001 as executed with an invented cause.)* |
| D54 | Host crashes | Agent 2 kills a host that crashed at start and starts it **once more**; a second crash is LOAD-000 `executed: true`, `error_dialog_seen: true` (FAIL). In `finally`, code saves Windows' crash records for the host's processes (Application Error, WER, .NET Runtime) to `evidence/host_crash_events.txt`, logs them, and the report shows them. *(Run 20261013-175002: Plant 3D crashed in `ODISSDK.dll` at start; the cause turned out to be D55.)* |
| D55 | Windows-MCP environment | The MCP SDK starts a stdio server with only 12 environment variables, and every program Windows-MCP starts inherits them. Without `ProgramData`, `ProgramFiles`, `CommonProgramFiles`, … Plant 3D crashed in `ODISSDK.dll` on every pipeline start (runs 20261013-175002, -184220; reproduced with the SDK's environment). Code now passes the server **this process's normal environment, minus anything named like a secret** (`KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, `AUTH`, `COOKIE`), so API keys never reach Windows-MCP or the host (`execute/windows_mcp.py: server_env`). |
| D56 | Dialogs: Agent 2 decides | **Agent 2 decides how to handle each dialog**, as a careful tester would: read it (Snapshot), take a Screenshot, judge what it is (notice, load/trust prompt for the app, error while the host still works, crash, something with a lasting effect or unclear) and pick the button with the **smallest lasting effect**, so the test can go on. The skill gives principles and examples, not a fixed list; never "Always …", "Don't show again" or a settings change; something with a lasting effect or unclear is not agreed to; the same dialog twice → stop LOAD. **Evidence and record use the existing workflow:** the screenshots (attached automatically) and the LOAD test's `notes` (title, text with an English gist, judgement, button, reason). No extra guardrail or dialog file. `error_dialog_seen` = an error, warning or crash was shown; a notice or load prompt is not an error. *(Run 20261014-111858: the plug-in's German notice "Hinweis" with only OK stopped LOAD under D49.)* |
| D57 | Test-case review | After Agent 1 writes `testcases.yaml` and `understanding.md`, the console lists every test (ID, category, priority, title) with both file paths and asks **"Go ahead and run them on this machine? [y/n]"**. `y` continues to the preflight; `n` (or Ctrl+C / end of input) ends the run as `STOPPED: test plan not approved at the review`, before anything is installed. Without a console (unit tests, redirected input) the run continues and the log says so. *(Requested by the seniors, 2026-10-14, so a recorded demo shows the plan being checked before it runs.)* |

### 2.5 UI claims judged by an LLM, leftovers, covered UI, generic skills (D58–D67, built 2026-10-14)
Details and reasoning: [`LOAD_TESTS_PLAN.md`](LOAD_TESTS_PLAN.md) §9 (L20–L26). *(Run 20261014-124157: the guide says tab "P&ID Exporter"; the plug-in shows "P&ID Connector" with groups Tools / Settings, and its own DLLs contain exactly those words.)*

| # | Topic | Decision |
|---|---|---|
| D58 | LLM judge for UI claims | A separate model call with a fresh context (same `OPENAI_MODEL`) decides tests whose expectation is a UI claim. It sees only the claim, its quotes, the test's screenshots, the host-window Snapshot text and Agent 2's notes (as the executor's description, not proof). Facts stay with code (D7). |
| D59 | Claims, not strings | New check **`judged`** (value = the documented claim in plain words, with citations). Agent 1 writes LOAD-001 (entry point present) and LOAD-002 (documented items reachable). `seen_in_ui` is retired. Generic: the claim is whatever the documents describe. |
| D60 | The app's own UI text | S1 extracts the readable text of the installer's binaries into a new citable source **`U1`** (hints; may contain related products' text). Agent 1 cites it next to the documents and raises an open question on any disagreement. |
| D61 | The judge's rule and guards | Matches the documents → PASS; matches only `U1` → **PASS with a finding** "documentation mismatch"; neither → FAIL; can't tell → NEEDS_REVIEW. The judge must name an attached screenshot, otherwise ERROR; no screenshots or a failed call → ERROR. The judgement is stored in `results.json`. |
| D62 | Generic exploration by Agent 2 | Agent 2 opens only what **reveals** more UI and never what **acts**; a Screenshot of every state; the notes describe what was seen. No UI-type specifics in code or skills. |
| D63 | Findings in the report | Every judged test shows the claim, verdict, reason, findings and screenshot; a **Findings** section lists all findings of the run. |
| D64 | Nothing left behind (UNIN-000) | A **built-in test written and decided by code** for every app. The preflight lists the registry Software keys (HKCU, HKLM, WOW6432Node) and the user, data and program folders (+ the app's install roots) two levels deep. After Agent 2, with the host closed and before cleanup, code lists them again. New entries still there are leftovers: in the install roots or machine-wide → **FAIL** (`program_leftovers` = 0 expected); per-user settings → **PASS with a finding**. Windows' own places and the host's `profile_ignore` (host notes) are skipped. Read-only: code never deletes leftovers. A diff only sees what this run created; clean machines come later (ADR-010). *(Run 20261014-153924: the plug-in left `HKCU\Software\PidConnectorExport`, `%LocalAppData%\PidConnectorExport\license.dat` and a .NET `user.config` with its language setting, which changed its dialog's language in later runs.)* |
| D65 | Covered or cut-off UI | Agent 2 makes the claimed UI visible with **view-only changes, smallest first** (maximize, expand, scroll, move/collapse/auto-hide a covering panel; close a panel only if it isn't part of the test and can be reopened), undoes them and notes them, and checks that its screenshots show every element the claim names. The judge: **hidden is not missing**, a covered element is NEEDS_REVIEW, never FAIL. *(Run 20261014-153924: the Project Manager palette covered most of the ribbon.)* A clean host profile per run is a later option. |
| D66 | The judge's own client | The judge runs every call in its own event loop with its own OpenAI client (`Settings.fresh_model()`). The SDK's shared client stayed tied to Agent 2's closed `asyncio.run()` loop (run 20261014-153924: `Event loop is closed`). |
| D67 | Generic skills, host knowledge as data | **The skills contain principles only, no host or app knowledge.** A host profile (`skills/hosts/<id>.md`) is **front matter only**: `host_process` (D43) and an optional `releases` table (host version ↔ the release numbers manifests use). Its prose (recognition hints, registry recipes, start-page and dialog examples, Ctrl+N/template hints, ribbon notes) was removed; Agent 1 recognises the host from the app's own manifest and documents, and Agent 2 handles the host UI from generic principles (D56, D62, D65). A test (`test_skills`) rejects host or app names in skill prose. *(Experiment 2026-10-14: run 20261014-175347 with generic skills gave the same 14 PASS and the same findings as the case-tuned run 20261014-162644, in 5.2 instead of 7.2 Agent 2 minutes. Needs `OPENAI_MODEL=gpt-5.5`-class models; gpt-4o-mini failed even with the case-tuned skills.)* |

**Agent 2 resolves placeholders** (`${PLUGIN_DIR}` etc.) during its ENV tests and returns them in its final output.

---

## 3. High-level flow (one F5 run)

```
 F5  →  mpagent inputs/<app>                       run folder: runs/<app>/<ts>/   (run.log, trace.jsonl)

 DESIGN SIDE (no machine access)
   S0 Intake (code)  →  S1 Installer static read (code)
        │
        ▼
   ┌──── AGENT 1: Test Designer (OpenAI, no tools) ─────┐
   │ skills: test-design + all hosts/*.md (catalogue)   │
   │ decides host_id, then designs the tests            │
   │ output_type = TestPlan → self-check → retry ≤2     │──► still failing → STOPPED (exit 1)
   └────────────────────────────────────────────────────┘
        │ testcases.yaml, understanding.md
 EXECUTION SIDE
        ▼
   REVIEW (console): test cases listed → "Go ahead? [y/n]"  └─ n → STOPPED (exit 1)
        │
        ▼
   PREFLIGHT (code): elevated? · Windows-MCP = 13 tools? · ENV-000 plug-in not installed? · host not running?
        │                                                   └─ any fail → STOPPED (exit 1)
        ▼
   ┌──── AGENT 2: Test Executor (OpenAI + Windows-MCP) ──┐
   │ skills: windows-installer + evidence + hosts/<id>   │
   │   (+ host-interaction when the plan has LOAD tests) │
   │ one session: ENV → INST (silent) → LOAD (start host,│──► record_observation → observations.json
   │   new document, Snapshot, kill host) → UNIN (silent)│
   │ guardrails: PowerShell allow-list, read-only,       │
   │   install once, repeat limit, host-only App launch, │
   │   no uninstall while host runs; results capped      │
   │ limits: 150 turns · 120 s/tool · 40 min             │
   └───────────────┬─────────────────────────────────────┘
                   │ MCP stdio (13 allowed tools)
                   ▼
            Windows-MCP ──► Windows + host app + plug-in
        │
        ▼
   KILL HOST (code, finally) → CLEANUP (code, finally): msiexec /x only if still installed
        │
   VERDICT ENGINE (code: facts; LLM judge: UI claims, D58) → results.json → report.html (+ Findings)
        │
   run.log: COMPLETED … / STOPPED …   (exit 0 / 1 / 2)
```

---

## 4. Design side

### S0. Intake (existing code: keep)
`design/intake.py`, unchanged. It sorts files by type, extracts text with numbered lines (D1, D2…), hashes every file, reads the claimed signer, and writes `intake_manifest.json` + `documents/`.

### S1. Installer static read (existing code: keep)
`design/static_read.py` and `design/msi.py`, unchanged. They read the MSI without running it and write `installer_facts.json`: properties, files, install roots, custom actions, registry entries, embedded docs, and bundle manifest if present.
- The `BundleManifest` model is a **host-specific reader** (Autodesk `PackageContents.xml`). It stays as an optional reader. The core must not depend on it.
- EXE and ZIP readers come later.

### Host lookup (done by Agent 1, no separate code step)
Keywords can't always identify the host from a description, so **Agent 1 decides it** as part of its single pass:
- Code loads every `skills/hosts/*.md` file and gives Agent 1 the catalogue: the `host_id` and the content of each file.
- Agent 1 reasons over the documents **and** the installer facts (e.g. `PackageContents.xml` says `Platform="Plant3D"`), then sets:
  - `app.host_id` to a catalogue entry;
  - `none` for a standalone Windows app;
  - `unknown` if it can't tell, with an open question saying why.
- It also sets `app.host_evidence`, with source quotes that are checked like every other citation.
- The chosen `host_id` is recorded in `testcases.yaml`. Agent 2 loads `skills/hosts/<host_id>.md` from there. For `unknown`, it loads only the generic skills.
- Later, when there are many host notes: replace the full catalogue with a short index plus a local read-only tool that loads one note on request (a knowledge file, not machine access).

### Agent 1: Test Designer (new)

| Item | Spec |
|---|---|
| Agent | `agents.Agent(name="test-designer", instructions=<skills>, output_type=TestPlan, model=$OPENAI_MODEL)` |
| Tools | **None** |
| Input message | An **evidence pack**, with each source wrapped as untrusted evidence and given numbered lines: `D1…` (documents), `I1…` (documents embedded in the installer), and **`F1` = `installer_facts.json` rendered as one `key = value` per line** (e.g. `properties.ProductCode = {…}`, `bundles[0].runtime_requirements[0].platform = Plant3D`). Installer facts are therefore cited and quote-checked exactly like documents. |
| Instructions | `skills/test-design/SKILL.md` + the host notes catalogue (all `skills/hosts/*.md`) |
| Output | `TestPlan` (§6.1). Code writes `testcases.yaml` (+ `.json`) and renders `understanding.md` from it. |
| Self-check (code) | (1) schema valid; (2) every `source.quote` really appears in the cited document text; (3) every `${PLACEHOLDER}` used is listed in `required_env`; (4) **basic coverage (D24):** an INST test observing the install exit code, an INST test observing that the Uninstall entry exists, and a UNIN test observing that the entry is gone; (5) every `expected.check` is a supported type and every `expected.key` is in that test's `observe`; (6) `host_id` is a catalogue entry, `none` or `unknown`, and `host_evidence` quotes are real; (7) test IDs are unique and every precondition refers to an existing test or `ENV-000`. On failure, the error list is sent back and the agent retries, at most 2 times. Still failing → **STOPPED** (D18). |
| Rules | Test the plug-in, not the host's API. Never guess (`null` + an open question). Machine values are always placeholders. Every test cites its source. Don't write the "already installed" check (it's ENV-000, built in). Make host-dependent tests depend on the host ENV test via `preconditions`. |

After a successful self-check, code **adds ENV-000** to the plan (`origin: built-in`) and makes every INST test depend on it.

---

## 5. Execution side

### Preflight (code, new)
Runs right after Agent 1, before Agent 2. Each check logs one line in `run.log`.

| Check | How | On failure |
|---|---|---|
| Elevated | Windows token check (e.g. `IsUserAnAdmin`) | `STOPPED: not running as administrator — start Visual Studio as administrator` |
| Windows-MCP | Start the pre-installed, pinned Windows-MCP with `--tools <13>`; list its tools | `STOPPED: Windows-MCP not found / tool list mismatch` |
| **ENV-000** plug-in not installed | Read both Uninstall registry hives (incl. WOW6432Node) for the ProductCode, or the DisplayName as a fallback, from `installer_facts` | Recorded as ENV-000 FAIL; INST/UNIN BLOCKED; `STOPPED: plug-in already installed — uninstall it manually` |

### Agent 2: Test Executor (new)

| Item | Spec |
|---|---|
| Agent | `agents.Agent(name="test-executor", instructions=<skills>, mcp_servers=[windows_mcp], tools=[record_observation], model=$OPENAI_MODEL)` |
| MCP server | `MCPServerStdio` launching the **pre-installed** Windows-MCP **0.8.6** (`windows-mcp serve --transport stdio --tools "<allow-list>"`, built in `execute/windows_mcp.py`), plus `tool_filter=create_static_tool_filter(allowed_tool_names=[…])`. Per-tool timeout: `AGENT2_TOOL_TIMEOUT_S` (120). |
| Input message | The whole `testcases.yaml` (incl. ENV-000's result), the run folder path (where msiexec writes its logs), the installer path, and the **"App under test" block** (D38) |
| Instructions | `skills/execute/windows-installer.md` + `skills/execute/evidence.md` (+ `skills/execute/host-interaction.md` when the plan has LOAD tests) + `skills/hosts/<host_id>.md` |
| Order | ENV (and resolve every `required_env` placeholder) → INST (**silent msiexec /i**, D26) → UNIN (**silent msiexec /x**, D27). Run every test; don't skip because of a precondition (D25). |
| Reporting | Call **`record_observation`** right after each test (D30). The final output is only `{ done: true, env: {…} }`. |
| Limits | `max_turns` 150; total wall-clock limit 20 min (`AGENT2_MAX_TURNS`, `AGENT2_TIMEOUT_MIN`) (D29) |

### `record_observation` (local function tool, new)
`record_observation(test_id, executed, observed: [{key, value}], evidence: [paths], notes)` checks that `test_id` exists in the plan (ENV-000 is refused: code records it) and that every evidence path is an existing file inside the run folder. It then adds the screenshots taken since the previous call and appends to `observations.json`, overwriting an earlier entry for the same test, except that an `executed: true` entry is never replaced by `executed: false`, and an identical repeat is not saved again (D30). It has no access to the machine.

### Windows-MCP tool allow-list (13)

| Tool | Used for |
|---|---|
| **PowerShell** | `Start-Process -FilePath msiexec.exe -ArgumentList '/i',…,'/l*v','<run>\evidence\install.log' -Wait` and the same with `'/x','<ProductCode>'` → `uninstall.log`; then `Select-String` on the log for the real exit code (D26, D27); `Get-AuthenticodeSignature`, OS version and admin check (allow-listed commands only, D32) |
| **Registry** | Host detection; Programs & Features entry present or gone (all three Uninstall keys, including WOW6432Node). Read only (D33). |
| **FileSystem** | Required folders exist; installed files present; manifest readable; files gone after uninstall. **Read-only** (D33). |
| **Process** | Installer or host running; close a stuck installer |
| **App** | Start programs by full path (next planned use: open the host for the plug-in screenshot test) |
| **Snapshot** | Read the window's accessibility tree (the agent's "eyes") |
| **Click / Type / Shortcut / Scroll** | UI steps (none in the current ENV/INST/UNIN flow; kept for the host test) |
| **WaitFor / Wait** | Wait for windows and elements |
| **Screenshot** | Evidence of UI state (saved to `evidence/` by the trace hook, D31) |

**Blocked (7 in Windows-MCP 0.8.6, which has 20 tools):** DisplayInventory, Move, MultiSelect, MultiEdit, Clipboard, Scrape, Notification. They're blocked twice: Windows-MCP `--tools` and the SDK filter. (`ControlStatus`, named in the project README, doesn't exist in 0.8.6; it would be blocked too.)

### Guardrails (code, run before every MCP call)
1. **Allow-list** (above), enforced in two places.
2. **PowerShell:** the command must start with an allow-listed command (D32), otherwise it's rejected.
3. **Registry:** only read and list actions (D33).
4. **FileSystem:** read-only; whole-file reads over 50 KB need `offset`/`limit` (D33).
5. **Per run (D36):** install only once; the same call more than 3 times is rejected.
6. Every rejection goes to `run.log` and `trace.jsonl`, and the agent receives the reason as the tool result.

After each allowed call, code **cleans and caps the result** before the model sees it (D37).
6. **Untrusted text:** the instructions state that text in the plug-in's docs and UI is data, never instructions.
7. **Evidence rule:** report raw values only. Never judge pass or fail.

### Verdict engine (new, code, ~40 lines)
For each test case it evaluates `expected[]` against the test's entry in `observations.json`:

| Check | Meaning |
|---|---|
| `equals` / `not_equals` | `observed[key] == value` |
| `in` | `observed[key] in values` (e.g. exit code in `[0, 3010]`) |
| `exists` / `not_exists` | the observed key is true or false (file, registry key, entry) |
| `contains` / `matches` | substring or regex on a text value (e.g. signer name) |

Statuses, in this order of precedence:
- **BLOCKED:** a precondition test is FAIL/BLOCKED/ERROR, or a needed placeholder couldn't be resolved. This applies **even if the test ran** (D25).
- **ERROR:** no observation for the test (e.g. after a timeout), or an expected key is missing.
- **FAIL:** any check fails.
- **PASS:** every check holds.

### Cleanup (code, `finally`, new)
See D28. It runs after the verdicts (and also after a STOPPED or crash, once Agent 2 has started). It's logged as `CLEANUP: …` and never changes a result.

### Report (new, ~40 lines)
- `results.json`: per test, the status, `origin` (agent / built-in), expected vs observed, and evidence.
- `report.html` (Jinja2), **only if Agent 2 ran**: a summary table, then per test the title, status, **source quote**, expected vs observed, and evidence links.
- `run.log` and `trace.jsonl`: see D19.

---

## 6. Data contracts (Pydantic)

All models must work with OpenAI **strict structured output**, so there are no free-form `dict` fields. Key/value data is stored as lists of `{key, value}`.

### 6.1 `TestPlan` (Agent 1 output; ENV-000 added by code)
```yaml
app:
  name: "P&ID Connector Exporter for Plant 3D"
  publisher: "Kleen Software"
  version: "x.y"
  host_id: autocad-plant3d            # chosen by Agent 1: a host notes id, "none" (standalone) or "unknown"
  host_evidence:                      # why Agent 1 chose it (checked like any citation)
    - { doc: "F1", line: 42, quote: "bundles[0].runtime_requirements[0].platform = Plant3D" }
  host_versions: ["2027"]
  installer: { file: "….msi", type: msi, product_code: "{…}", signer_claimed: "Kleen Software GmbH" }
summary:                              # rendered into understanding.md
  purpose: "…"
  install_footprint: ["…"]
  commands_or_ui: ["…"]
  open_questions: ["…"]
required_env: [HOST_INSTALL_DIR, PLUGIN_DIR]
testcases:
  - id: ENV-000                       # added by code after the self-check
    origin: built-in
    category: ENV
    title: "Plug-in is not installed before the test"
    observe: [preinstalled_entry_exists]
    expected: [{ key: preinstalled_entry_exists, check: not_exists }]
  - id: INST-002
    origin: agent
    category: INST                    # ENV | INST | UNIN   (LOAD | FUNC later)
    title: "Programs and Features entry is created"
    source: { doc: "F1", line: 3, quote: "properties.ProductName = …" }
    preconditions: [ENV-000, INST-001]
    steps:                            # plain-language intents for Agent 2
      - "Look up the Uninstall registry entry whose DisplayName matches the product name"
    observe: [uninstall_entry_exists, display_version]   # keys Agent 2 must report
    expected:
      - { key: uninstall_entry_exists, check: exists }
      - { key: display_version, check: equals, value: "x.y" }
    priority: P1
```

### 6.2 `observations.json` (written by `record_observation`) + Agent 2 final output
```yaml
# observations.json: one entry per test, appended as Agent 2 goes
- test_id: INST-002
  executed: true
  observed: [{ key: uninstall_entry_exists, value: true }, { key: display_version, value: "x.y" }]
  evidence: ["evidence/INST-002_registry.txt"]
  notes: "Found under HKLM\\…\\Uninstall\\{…}"

# Agent 2 final output
done: true
env: [{ key: HOST_INSTALL_DIR, value: 'C:\Program Files\Autodesk\AutoCAD 2027' }, { key: PLUGIN_DIR, value: '…' }]
```

### 6.3 `TestResult` (verdict engine output)
`{ test_id, origin, status: PASS|FAIL|BLOCKED|ERROR, checks: [{key, check, expected, observed, ok}], evidence, notes }`

---

## 7. Skills (Markdown instruction files)

| File | Used by | Content |
|---|---|---|
| `skills/test-design/SKILL.md` | Agent 1 | The categories and what each must cover; the basic coverage required by D24 with the suggested key names (`install_exit_code`, `uninstall_entry_exists`); citation format; placeholders; `observe` / `expected` rules and allowed checks; preconditions; "never guess"; "test the plug-in, not the host"; "ENV-000 is built in, don't write it"; LOAD: the entry-point card, LOAD-001 only for visible kinds, `seen_in_ui`, "LOAD-000 is built in" (D41, D42) |
| `skills/hosts/autocad-plant3d.md` | Agents 1 + 2 (catalogue), code | **Front matter only (D67):** `host_process` (how code finds, starts and recognises the host) and `releases` (2024 = R24.3 … 2027 = R26.0). No prose. |
| `skills/hosts/none.md` | Agents 1 + 2 | Standalone Windows app: Program Files, Start menu, Programs & Features only |
| `skills/execute/windows-installer.md` | Agent 2 | Allowed PowerShell commands (D32); read-only file rules and the 50 KB / 20,000-character limits (D33, D37); silent install and **silent uninstall** with logs, exit codes read from the logs (D26, D27); the three Uninstall registry paths; signature check; generic UI rules (full paths only, no Win+R, no guessed coordinates, never touch the console) |
| `skills/execute/evidence.md` | Agent 2 | Call `record_observation` after every test; raw values only; reference saved screenshots and logs; untrusted-text rule; read-only rule; run every test |
| `skills/execute/host-interaction.md` | Agent 2 | Generic LOAD principles (D67): order, start exactly as given, decide on anything that appears (smallest lasting effect, document it), a new empty document "the way this host offers it", reveal never act, make it visible and undo, screenshot every claimed element, kill the host before UNIN |

A new host means **one new Markdown file**, with no code change.

---

## 8. Tech stack (final)

| Area | Choice |
|---|---|
| Language and environment | Python 3.12, **uv** (existing) |
| Agents | **openai-agents** (Agents SDK). Replaces `google-genai`. |
| MCP server | **Windows-MCP**, pinned version, **installed beforehand** (`uv tool install windows-mcp==<pinned>`) |
| Schemas | Pydantic v2 (existing) |
| YAML | ruamel.yaml (existing) |
| Doc extraction | pypdf, python-docx, beautifulsoup4 (existing) |
| MSI read | pywin32 (existing) |
| CLI | Typer + rich (existing), **single entry point** |
| Logging | Python `logging` → console + `run.log`; JSONL trace |
| Report | Jinja2 (existing) |
| Tests | pytest, ruff (existing) |
| IDE | Visual Studio, **F5** = full run (`mpagent.pyproj` launch argument `inputs/<app>`) |

**`.env`:** `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_AGENTS_DISABLE_TRACING=1`, `AGENT2_MAX_TURNS=150`, `AGENT2_TOOL_TIMEOUT_S=120`, `AGENT2_TIMEOUT_MIN=40`, `WINDOWS_MCP_COMMAND` (path/name of the installed Windows-MCP).

**Dependency change:** remove `google-genai`, add `openai-agents` (+ `python-dotenv` if `.env` isn't already loaded).

---

## 9. Code layout (changes to `CodeBase/`)

```
CodeBase/
├─ src/mpagent/
│  ├─ cli.py                    # single entry: mpagent <input_dir> → pipeline.run()
│  ├─ pipeline.py               # NEW: S0 → S1 → Agent 1 → preflight → Agent 2 → verdict → report; finally cleanup; exit codes
│  ├─ config.py                 # NEW: .env loading, model name, limits, MCP command
│  ├─ runlog.py                 # NEW: run.log + console logging, trace.jsonl hooks, screenshot saving
│  ├─ models.py                 # existing; + TestPlan, Observation, TestResult; + EntryPoint, HostProcess (v2.3)
│  ├─ hostnotes.py              # BUILT (v2.3): host notes front matter → HostProcess (shared by design and execute)
│  ├─ design/
│  │  ├─ intake.py              # existing (keep)
│  │  ├─ static_read.py, msi.py # existing (keep)
│  │  ├─ evidence.py            # BUILT: evidence pack (D*, I*, U1 = the app's UI text, F1 = installer facts)
│  │  ├─ ui_text.py             # BUILT (D60): readable UI text from the installer's binaries → U1
│  │  ├─ agent1.py              # BUILT: Agent 1 + retry + writers + ENV-000 injection
│  │  ├─ selfcheck.py           # BUILT
│  │  └─ templates/             # BUILT: understanding.md.j2
│  └─ execute/
│     ├─ windows_mcp.py         # BUILT: pinned version, 13-tool allow-list, server factory, tool-list check, save_images,
│     │                         #        RecordingMCPServer + CallRecorder (traces every MCP call, saves screenshots)
│     ├─ preflight.py           # BUILT: admin, Windows-MCP tool list, ENV-000, host not running (v2.3)
│     ├─ host.py                # BUILT (v2.3): find the host executable, running host PIDs, kill the host
│     ├─ ui_tree.py             # BUILT (v2.3): Snapshot UI-tree parser for window_in_ui
│     ├─ judge.py               # BUILT (D58, D66): the LLM judge for `judged` UI claims
│     ├─ footprint.py           # BUILT (D64): before/after footprint for UNIN-000 "nothing left behind"
│     ├─ observations.py        # BUILT: observations.json (shared by preflight and record_observation)
│     ├─ agent2.py              # BUILT: Agent 2 + Windows-MCP + record_observation + limits
│     ├─ guardrails.py          # BUILT: PowerShell allow-list, Registry/FileSystem/Process/App/Wait rules
│     ├─ verdict.py             # BUILT: PASS/FAIL/NEEDS_REVIEW/BLOCKED/ERROR from observations (code only)
│     ├─ cleanup.py             # BUILT: msiexec /x if the app is still installed at the end
│     ├─ report.py              # BUILT: results.json + report.html
│     └─ templates/             # BUILT: report.html.j2
├─ skills/                      # NEW: Markdown skills (§7)
└─ tests/                       # BUILT: test_pipeline, test_windows_mcp, test_models, test_skills, test_selfcheck,
                                #        test_agent1, test_guardrails, test_preflight, test_agent2, test_verdict,
                                #        test_host, test_ui_tree (fixtures/: a real Snapshot UI tree)
```

Nothing in `design/` imports from `execute/`. `pipeline.py` is the only module that uses both.

**Entry point (F5 and terminal are the same):**
```bash
uv run mpagent inputs/pid-connector-exporter
```

**Run folder:** `runs/<app>/<ts>/`
- `run.log`, `trace.jsonl`
- `intake_manifest.json`, `documents/`, `installer_facts.json`
- `testcases.yaml`, `testcases.json`, `understanding.md`
- `observations.json`, `results.json`, `report.html` (if Agent 2 ran), `evidence/`

---

## 10. Build steps

| # | Step | Done when |
|---|---|---|
| 1 | Dependencies, `config.py`, `runlog.py`, single-entry `cli.py` + `pipeline.py` skeleton (S0 + S1 wired) | F5 runs S0 + S1 and writes `run.log` with a final status line |
| 2 | Windows-MCP: pinned install, then a smoke test that lists the tools and takes one screenshot | Exactly the 13 tools visible; it's clear whether screenshots are saved as files (D31) |
| 3 | Models: `TestPlan`, `Observation`, `TestResult` | Unit tests round-trip YAML and JSON; the SDK accepts `TestPlan` as a strict `output_type` |
| 4 | Skills: the 5 Markdown files | Reviewed by the team |
| 5 | Agent 1 + self-check (incl. D24) + writers + ENV-000 injection; STOPPED path | F5 produces a valid `testcases.yaml` for P&ID Exporter; a forced self-check failure stops with exit 1 |
| 6 | Preflight + guardrails | Unit tests for every guardrail rule; F5 without admin stops with exit 1 |
| 7 | Agent 2 + `record_observation` + limits + cleanup | F5 installs silently, uninstalls via the UI, fills `observations.json`; a forced timeout leads to ERROR + cleanup |
| 8 | Verdict engine + report | `results.json` + `report.html` with correct PASS/FAIL/BLOCKED/ERROR |
| 9 | End-to-end demo | One F5 from inputs to `COMPLETED` line and report |

---

## 11. Verification (demo acceptance)

1. **Unit:** `uv run pytest`. Self-check catches a fake quote, a missing placeholder and missing basic coverage. Verdict engine covers every check type and the BLOCKED/ERROR precedence. Guardrails reject non-allow-listed PowerShell commands, registry writes and file deletes.
2. **Happy path (F5):** with Plant 3D 2027 installed and the plug-in **not** installed: ENV PASS, INST PASS (exit code 0, entry and files present), UNIN PASS (silent uninstall exit code 0, entry and files gone). Final line `COMPLETED`, exit 0, no CLEANUP action. *(Achieved in run 20261013-152426: 3 PASS, 11 tool calls, about 80 s.)*
3. **Already installed:** install the plug-in by hand, then F5 → ENV-000 FAIL, `STOPPED: plug-in already installed`, exit 1, nothing installed.
4. **Not admin:** F5 from a non-elevated VS → `STOPPED: not running as administrator`, exit 1, the design outputs still exist.
5. **Interrupted run:** force a timeout during UNIN → missing tests are ERROR, CLEANUP runs `msiexec /x`, and the plug-in is gone afterwards.
6. **Safety:** the trace shows only allowed tools; guardrail rejections are logged.
7. **Evidence:** every executed test in `report.html` links to a log, a registry dump or a screenshot.

---

## 12. Risks (accepted for the demo)

| Risk | Mitigation |
|---|---|
| PowerShell, Registry and FileSystem can change the machine | Allow-list of tools; PowerShell command allow-list; read-only Registry; no deletes; admin dev machine accepted; VM later |
| Prompt injection from third-party docs or UI text | Agent 1 has no tools; Agent 2 treats text as data; guardrails in code |
| UAC dialog can't be automated | Preflight requires an elevated VS; silent install and uninstall |
| UI steps are fragile, and a confused model can click the wrong item | Uninstall is silent (D27); UI is only for screenshot-type tests; generic UI rules in the skill; screenshots, time limits |
| A weak model (gpt-4o-mini) loops, reorders tests or writes thin plans | Self-check (D24), per-run guardrail rules (D36), no-overwrite of observations (D30), app facts (D38); a stronger model if available |
| Large tool output overflows the model's context | Results cleaned and capped (D37); large whole-file reads rejected (D33) |
| Windows-MCP is a community project | Pinned version, installed beforehand; preflight checks its tool list |
| LLM runs vary slightly | Verdicts by code; the plan is saved; a new plan each F5 is accepted (D16) |
| Agent 2 skips a test in a long session | `record_observation` per test; missing observations → ERROR |
| A run leaves the plug-in installed | Cleanup in `finally`; otherwise the next run stops at ENV-000 |

---

## 13. Later phases

From our v0.3 design and from `AppStore automation/`:
1. **LOAD / FUNC** tests: host launch, UI entry visible, one documented feature, using Windows-MCP UI tools.
2. **Fixed Level 1 generic suite** (no LLM) for the checks that are the same for every app.
3. **Test-data catalogue** (approved sample files) for FUNC tests.
4. **NEEDS_REVIEW** status and a human reviewer report.
5. **Optional human review gate.**
6. **VM / Windows Sandbox isolation** with checkpoint reset.
7. **Snapshot diff** to find files left after uninstall.
8. **Feedback pass:** Agent 2's ENV findings go back to Agent 1.
9. **Record and replay** of MCP calls (for LLM-free reruns).
10. **EXE / ZIP installer readers**; submission bundle with `publisher_test_notes`.
11. **Host command channels** (e.g. COM) declared in host notes.
12. **Robot or TestRail export** from `testcases.yaml`.
13. **Testing both uninstall paths** (silent and UI) in one run, with a reinstall in between.
