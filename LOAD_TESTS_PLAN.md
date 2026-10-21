# LOAD tests: is the app loaded by its host, and is its entry point there?

> **This document covers the LOAD tests only.** Functional tests (running the app's documented features) have their own plan: [`FUNC_TESTS_PLAN.md`](FUNC_TESTS_PLAN.md).
> **Status (2026-10-14): built and verified.** Phase 1 (grill-me review 2026-10-13, Q1–Q17) and Phase 1b (LLM judge, leftovers, covered UI, generic skills, §9) are implemented. Live runs with generic skills: **20261014-175347** and **20261014-194215**, both 14 PASS (§10). Branch `Dev-FunctionalTest`.
> **Recorded in:** [`ARCHITECTURE.md`](ARCHITECTURE.md) D40–D67 and [`ADR.md`](ADR.md) ADR-033–046. Decisions here are numbered L1–L29.
> **How to read it:** §1 is the current design. §3–§8 are the Phase 1 design as agreed on 2026-10-13; parts of it are superseded (marked in the tables) by Phase 1b in §9. §10 lists the live runs.
> **Rule kept from D1/D67:** nothing in the code or the skills names a product. App knowledge comes from the app's documents and files; host knowledge only from the host profile's front matter (data). The P&ID Connector Exporter examples are only examples.

---

## 1. Goal and current design

A run tests **ENV → INST → LOAD → UNIN**. LOAD sits between install and uninstall:

```
ENV → INST → LOAD (start the host → new empty document → show the app's entry point) → kill host → UNIN
```

| Test | Written by | Decided by | Example for the P&ID Connector Exporter |
|---|---|---|---|
| **LOAD-000** host ready with a new document | **code** (built-in) | **code**: `window_in_ui` on the raw UI tree (host window, new document); Agent 2's report for dialogs | the Plant 3D main window with `Drawing1.dwg` |
| **LOAD-001** the documented entry point is present | **Agent 1**, a cited claim | **LLM judge** from the screenshots (`judged`) | D2: *"a new tab called 'P&ID Exporter'"* → PASS with the finding "the app shows 'P&ID Connector'" |
| **LOAD-002** its documented items are reachable | **Agent 1**, a cited claim (when the documents name items) | **LLM judge** from the screenshots | D2: *"The 'Export' button…"* → PASS with the finding "the app shows 'Export P&ID'" |
| **UNIN-000** nothing left behind *(built-in, all apps)* | **code** | **code**: footprint before the install vs after the uninstall | 3 user-settings leftovers reported as findings |

**What makes it generic:**
- **Agent 1** takes app facts only from the app's documents and files: the documents (D*), files inside the installer (I*), the app's own UI text (U1) and the installer facts (F1). It writes claims in the documents' words.
- **Agent 2** follows generic principles (`host-interaction.md`): start the host exactly as given, decide on anything that appears, open a new empty document, *reveal never act*, make it visible, screenshot every claimed element.
- **The judge** decides each claim from the screenshots. If what's shown matches only the app's own text, that's PASS with a documentation-mismatch finding.
- **Code** decides the facts.
- **Host knowledge is data**: the host profile's front matter (`host_process`, `releases`).

A different app on the same host needs no change. A different host needs one small host profile.

**Out of scope here:** running the app's features → [`FUNC_TESTS_PLAN.md`](FUNC_TESTS_PLAN.md).

---

## 2. Background and research summary

- **No ready-made tool writes functional tests for desktop plug-ins.** [Playwright's planner/generator/healer agents](https://playwright.dev/docs/test-agents) work only on the web; our Agent 1 (planner) and Agent 2 (executor) already follow that pattern.
- **Host command channels** (e.g. AutoCAD startup scripts or COM `SendCommand`) can be more reliable than clicking, but they're host-specific (Phase 2 option, in host notes).
- **Oracles derived from docs hallucinate** ([survey](https://www.themoonlight.io/review/test-oracle-automation-in-the-era-of-llms)), so the verdict rests on **facts code can check** (window titles and element names in the raw UI tree), with a screenshot for humans.
- **On this machine:** Plant 3D 2027 is installed (`AcadLocation` in the registry). The plug-in installs **per user into `%AppData%\Autodesk\ApplicationPlugins\pidExport.bundle`**. Its manifest lists **no commands** and loads at startup, so its ribbon tab is the visible entry point.
- **The user guide names only one button.** It says the tab *"contains two new buttons"* but names only "Export". "Info" isn't in the documents.
- **Windows-MCP 0.8.6 facts (checked in the installed package):**
  - `App` has a mode **`launch_executable`** (exact path + argv + cwd) next to `launch` (by Start Menu name).
  - `WaitFor` polls the UI tree (`active_window`, `text_exists`, `element_exists`, …) with a `timeout`; `Wait` sleeps for `duration`.
  - `Snapshot` has **no window filter**. Its text has an *Opened Windows* table (every window title on the desktop, including browser tabs and chats) and a *UI Tree* that is structured per window: `window "<title>"` → `button "<name>"` …
- **Lessons from the live runs (2026-10-13):** a weak model (gpt-4o-mini) goes wrong whenever it has free rein in the UI (Win+R, guessed coordinates, wrong list row) and reports values it never saw. So the UI steps must be **short, fixed in a generic skill, and backed by code checks**. The last run (`20261013-152426`) did ENV + INST + UNIN in about 80 s with 12 MCP calls.

---

## 3. Decisions (Phase 1, agreed in the grill-me session, 2026-10-13; later changes marked per row)

| # | Question | Decision |
|---|---|---|
| L1 (Q1) | What does LOAD open? | The host + its **default new document** (a host-notes recipe, e.g. Ctrl+N → `Drawing1`). The app-specific context ("in a P&ID project with a drawing open") is about *using* the app: Agent 1 records it on the card as `use_context` for **Phase 2**. |
| L2 (Q2) | Who writes the LOAD tests? | **Code adds a built-in LOAD-000** (`origin: built-in`, no citation) whenever the host notes have `host_process`. **Agent 1 writes at most one test, LOAD-001** (the app claim, cited). *(After run 20261013-172934: exactly one is required when the entry point is visible.)* If the docs name no visible entry point, there is no LOAD-001 and Agent 1 adds an open question. |
| L3 (Q3) | What does LOAD-001 check? | **The label only** (e.g. the tab name). `entry_point.items` lists only **quoted** names. Anything the docs count but don't name becomes an open question. Clicking the tab or buttons is Phase 2. *(superseded by L21 (claims judged by an LLM; LOAD-002 for the items), 2026-10-14.)* |
| L4 (Q4) | How does `seen_in_ui` match? | Code parses the **UI Tree** section, takes the subtree of `window "<title>"` whose title matches the host's `main_window` regex, and passes only if an **element's quoted name equals the label** after normalising (casefold, collapsed whitespace, `&`/`&&` accelerator markers stripped). No host window → ERROR. Host window present but no such element → **NEEDS_REVIEW** if a screenshot exists, otherwise **FAIL**. *(superseded by L20/L23 (`seen_in_ui` is retired; the judge decides UI claims), 2026-10-14.)* |
| L5 (Q5) | Agent 2's value vs the UI tree | For `seen_in_ui` and `window_in_ui`, **the UI tree decides**. The "null value → ERROR" rule doesn't apply, and Agent 2's value is shown in the report only ("Agent 2 said: …"). **`record_observation` refuses** a test with such a check if no Snapshot was taken since the previous record ("take a Snapshot of the host window first"). *(partly superseded: for `window_in_ui` (LOAD-000) the UI tree still decides; UI claims go to the judge (L20), 2026-10-14.)* |
| L6 (Q6) | NEEDS_REVIEW | New status. Precedence within a test: BLOCKED → ERROR → FAIL → NEEDS_REVIEW → PASS. It **isn't PASS**, so dependents are BLOCKED. Shown in `results.json` counts, `summary_line` and the report (its own colour, screenshot inline). Exit codes are unchanged. **Don't design around it now** (see §9 open point). |
| L7 (Q7) | One or two Agent 2 sessions? | **One session.** A guardrail **rejects an uninstall `msiexec /x` while any host process is running**, telling Agent 2 to kill the host first. `finally` kills the host again as a backstop. No env hand-over, one `CallPolicy`. |
| L8 | Does UNIN depend on LOAD? | **No**, only on INST. The uninstall is always tested. |
| L9 (Q8) | Host facts for code; which programs Agent 2 may start | Each host-notes file gets **YAML front matter `host_process`** (§4.2). Code resolves the executable and passes the **exact path + args** in the App-under-test block. The guardrail allows `App` only as `launch_executable` with **exactly that path and those args**. `switch`/`resize` stay allowed; `launch` by name is rejected. `none.md` has no `host_process`, so there is no LOAD. |
| L10 (Q9) | Dialogs at host start | *(Updated 2026-10-14, ARCHITECTURE.md D56.)* **Agent 2 decides** how to handle each dialog, as a careful tester would: read it, screenshot it, judge what it is (notice, load/trust prompt for the app, error while the host still works, crash, lasting change or unclear) and choose the button with the smallest lasting effect so the test continues. Never "Always …", "Don't show again" or a settings change. Evidence = the attached screenshots; the record = the LOAD test's `notes`. *Was:* one-time yes for load prompts and "any other dialog stops LOAD", which failed LOAD-000 on the plug-in's harmless German notice "Hinweis" (run 20261014-111858). |
| L11 (Q10) | Who decides LOAD-000? | New check **`window_in_ui`**: a window or document/tab title matching a regex exists in the host window subtree (same parser as `seen_in_ui`). `host_started` uses `main_window`, and `document_opened` uses `new_document` (from host notes). Not found → FAIL. `error_dialog_seen` and `load_prompt_seen` stay Agent 2's report. |
| L12 (Q11) | Host already running at start | **Preflight stops**: "<host> is running (PIDs …). Close it and run again — Agent 2 not started." *(As built: since the preflight guarantees that no host process ran before, code kills every host process it finds later; no PID list is kept.)* `finally` order: **kill host → cleanup (msiexec /x) → verdicts → report**. |
| L13 (Q12) | How the host is closed | **Agent 2: one `Process kill`** of the host's processes after recording LOAD (never save, never use the host's own exit). **Code: kill only**, no graceful attempt (it would hang on "Save changes?"). The *Close without saving* host-notes section is kept for Phase 2. |
| L14 (Q13) | Waiting and time limits | The guardrail **caps `WaitFor.timeout` and `Wait.duration` at tool timeout − 15 s (105 s)** with the hint "call again to wait longer". The skill waits for the host window at most **twice** (≈ 3.5 min). `AGENT2_TIMEOUT_MIN` = **40** (shrink after real timings), `AGENT2_MAX_TURNS` stays 150. |
| L15 (Q14) | Which entry-point kinds get LOAD-001 | Only **`ribbon_tab`, `menu`, `toolbar`** (visible after start). For `command` or `own_window`, Agent 1 fills the card but writes no LOAD-001 and adds an open question. `Summary.entry_point` is nullable. *(still applies to LOAD-001; LOAD-002 added by L21, 2026-10-14.)* |
| L16 (Q15) | LOAD-000's precondition; failed install | LOAD-000 depends on **the INST test(s) observing `install_exit_code`** (D24 guarantees one exists). LOAD-001 depends on LOAD-000. If the recorded install exit code isn't a success value, Agent 2 **doesn't start the host**: it records LOAD as `executed: false` ("install failed") and goes on to UNIN (verdict: BLOCKED). |
| L17 (Q16) | Which Snapshot text the verdict reads | The recorder saves the **full raw text** of every Snapshot as `evidence/<n>_Snapshot_ui.txt`. `window_in_ui`/`seen_in_ui` read **only those files**, never the trace (capped at 20,000 characters) or the model's cleaned copy. What the model sees is unchanged in Phase 1. |
| L18 (Q17) | Build order | **The machine check is build step 1**: it fills the Plant 3D host notes and saves a real Snapshot that becomes the parser's test fixture. |
| L19 | Test-case review before execution | *(2026-10-14, requested by the seniors; ARCHITECTURE.md D57.)* After Agent 1 writes `testcases.yaml`, the console lists the tests and asks **"Go ahead and run them on this machine? [y/n]"**. `n` stops the run before the preflight, so nothing is installed. Without a console the run continues. |

---

## 4. Design (Phase 1, as built on 2026-10-13; see §9 for what changed)

### 4.1 Agent 1: entry-point card and LOAD-001 (generic) *(the `seen_in_ui` check is replaced by `judged` claims, L21)*
The test-design skill gets a LOAD section. Agent 1 fills `summary.entry_point` (nullable; shown in `understanding.md`), with every field cited:

| Field | Meaning | Example (derived, not hard-coded) |
|---|---|---|
| `kind` | `ribbon_tab` · `menu` · `toolbar` · `command` · `own_window` | `ribbon_tab` |
| `label` | the exact text the UI should show | `P&ID Exporter` |
| `items` | buttons or commands inside it, **only names that are quoted** | `[Export]` |
| `use_context` | what must be open to *use* the app (Phase 2), or `none` | "in a P&ID project and have a drawing open" |
| `sources` | citations for the fields above | D2: "a new tab called “P&ID Exporter”" |

Then, only if `kind` is `ribbon_tab`, `menu` or `toolbar`, it writes **LOAD-001**:

| Test | Observes | Expected | Preconditions |
|---|---|---|---|
| LOAD-001 entry point visible | `entry_point_label` | `seen_in_ui`, `value` = `entry_point.label` | `LOAD-000` |

New self-check rules:
- at most one agent-written LOAD test, and only if `entry_point.kind` is a visible kind;
- its `seen_in_ui` value equals `entry_point.label` and appears in a cited quote;
- its preconditions are exactly `[LOAD-000]`;
- UNIN tests don't depend on LOAD (L8);
- Agent 1 never writes LOAD-000 (code adds it).

### 4.2 Host notes: front matter + standard sections *(superseded 2026-10-14 by L29: front matter only)*
Each `skills/hosts/<id>.md` gets YAML front matter that **code** reads (agents see it too):
```yaml
host_process:
  locate: {registry_root: 'HKLM:\SOFTWARE\Autodesk\AutoCAD', value: AcadLocation,
           match_value: ProductName, match: '^AutoCAD Plant 3D \d{4}'}
  executable: acad.exe
  args: [/product, PLNT3D, /language, en-US]   # verify in step 1
  processes: [acad.exe]
  main_window: '^AutoCAD Plant 3D \d{4}'      # verify in step 1
  new_document: '^Drawing\d+(\.dwg)?$'        # verify in step 1
```
The field names are generic. A host found without the registry could later add a `locate.path` variant. `none.md` has no `host_process`.

The standard Markdown sections (for the agents) are:
- **Start:** what the front matter means; what the start screen looks like.
- **Ready signal:** the main window and what shows the host is ready.
- **Dialogs at start:** dialogs seen on the machine, as *examples* of the generic rule (L10), with the one-time answer.
- **Default new document:** the steps (e.g. Ctrl+N, default template) and the expected document title.
- **Where app entry points appear:** e.g. "plug-in ribbon tabs appear next to the built-in tabs; their names are in the UI tree".
- **Close without saving:** kept for Phase 2. Phase 1 uses Process kill.

### 4.3 Agent 2: host interaction (new generic skill) *(now principles only, L24/L29)*
`skills/execute/host-interaction.md` (generic, no product names):
1. If the install exit code you recorded isn't a success value, record each LOAD test as `executed: false` ("install failed") and go to UNIN.
2. Start the host with `App` `launch_executable`, using **exactly** the path and args from the App-under-test block. Wait with `WaitFor(condition=active_window, window_name=…)`, at most 105 s per call and at most twice.
3. Dialogs: apply the generic rule (L10). Accept a one-time load/trust/allow prompt for the app under test; for anything else, take a screenshot, record and stop LOAD.
4. Open the **default new document** (host notes). `Snapshot` the host, then record **LOAD-000** (`host_started`, `document_opened`, `error_dialog_seen`, `load_prompt_seen`).
5. `Snapshot` again, take a `Screenshot`, and record **LOAD-001** with the label you saw (or null). Don't click the app's tab or buttons.
6. **`Process kill`** the host's processes. Then go to UNIN.

The UI rules from the installer skill still apply: full paths only, no Run dialog, no guessed coordinates, never touch the console, stop after two failed attempts.

### 4.4 Code support (all generic)
- **`execute/host.py` (new):** reads the host notes' front matter; resolves the executable (`locate`); returns the launch line, process names and regexes; lists the running host PIDs; kills only PIDs that weren't there at preflight.
- **App-under-test block (D38):** adds the host's exact executable path, args, process names and main-window pattern.
- **Built-in LOAD-000:** added by code next to ENV-000 when `host_process` exists. Observes `host_started`, `document_opened` (`window_in_ui` with the host-notes regexes), `error_dialog_seen` (`not_exists`) and `load_prompt_seen` (no check). Precondition: the INST test(s) observing `install_exit_code`.
- **Recorder:** saves the full raw Snapshot text as `evidence/<n>_Snapshot_ui.txt` and attaches it, like screenshots (D31), to the next `record_observation`.
- **`record_observation`:** refuses a test with a `window_in_ui`/`seen_in_ui` check if no Snapshot text is pending.
- **UI-tree parser (`execute/ui_tree.py`, new):** splits the UI Tree into windows, finds the host window by regex, lists element names and document/tab titles in its subtree.
- **Verdict:** `window_in_ui` and `seen_in_ui` read only the attached `_Snapshot_ui.txt` files, and NEEDS_REVIEW is added (L4, L6, L11).
- **Guardrails:**
  - `App` only as `launch_executable` with the exact host path and args (`switch`/`resize` allowed, `launch` rejected);
  - `Process kill` allowed for msiexec and the host's processes;
  - an **uninstall `msiexec /x` is rejected while a host process runs**;
  - `WaitFor.timeout`/`Wait.duration` are capped at tool timeout − 15 s.
- **Preflight:** stops if a host process is already running, and notes the PIDs.

### 4.5 Pipeline order (Phase 1)
```
… preflight (+ host not running) → Agent 2, one session (ENV, INST, LOAD, kill host, UNIN)
  → finally: kill host (only new PIDs) → cleanup (msiexec) → verdicts → report
```

---

## 5. Changes by file (Phase 1; in `CodeBase/` unless noted)

| File | Change |
|---|---|
| `skills/hosts/autocad-plant3d.md`, `none.md` | Front matter + standard sections (§4.2); Plant 3D filled in and verified (build step 1) |
| `skills/test-design/SKILL.md` | LOAD section: entry-point card, visible kinds, LOAD-001 shape, `seen_in_ui`, open questions (L2, L3, L15) |
| `skills/execute/host-interaction.md` | **New**, generic (§4.3) |
| `src/mpagent/models.py` | `Category` + LOAD · `Check` + `window_in_ui`, `seen_in_ui` · `Status` + NEEDS_REVIEW · nullable `EntryPoint` card in `Summary` |
| `src/mpagent/design/selfcheck.py` | LOAD rules (§4.1); built-in LOAD-000 added next to ENV-000 |
| `src/mpagent/design/templates/understanding.md.j2` | Entry-point card |
| `src/mpagent/execute/host.py` | **New:** front matter, locate executable, PIDs, kill new PIDs |
| `src/mpagent/execute/ui_tree.py` | **New:** UI Tree parser (host window subtree, element names, titles) |
| `src/mpagent/execute/windows_mcp.py` | Recorder saves the raw Snapshot text per call and hands it over with the screenshots |
| `src/mpagent/execute/agent2.py` | Host facts in the App-under-test block; load `host-interaction.md`; `record_observation` Snapshot rule |
| `src/mpagent/execute/guardrails.py` | App rule, Process kill for host processes, no `msiexec /x` while the host runs, wait caps |
| `src/mpagent/execute/preflight.py` | Host-not-running check, PIDs noted |
| `src/mpagent/execute/verdict.py` | `window_in_ui`, `seen_in_ui`, NEEDS_REVIEW precedence |
| `src/mpagent/execute/report.py`, `templates/report.html.j2` | NEEDS_REVIEW colour and count; screenshot and "Agent 2 said" with LOAD results |
| `src/mpagent/config.py`, `.env.example` | `AGENT2_TIMEOUT_MIN` default 40 |
| `src/mpagent/pipeline.py` | `finally`: kill host before cleanup |
| `tests/` | New `test_host.py`, `test_ui_tree.py` (real Snapshot fixture from step 1); extend `test_selfcheck`, `test_verdict`, `test_models`, `test_guardrails`, `test_preflight`, `test_skills`, `test_agent2`, `test_windows_mcp`, `test_pipeline`, `test_report` |
| Repo root docs | ARCHITECTURE.md (D8 scope, new D40+), ADR.md, AGENT_TOOLING_REVIEW.md (App, Process, Wait rules) |

---

## 6. Build steps (Phase 1, on `Dev-FunctionalTest`)

| # | Step | Done when |
|---|---|---|
| 1 | **Machine check. Done through the live runs** (2026-10-13/14): title patterns, start page, plug-in notice, new document, palettes and the ribbon (not in the UI tree) were all seen; the host profile is now front matter only (L29). *Original scope:* registry lookup (`ACAD-A117:409`, `AcadLocation`) and launch args (`/product PLNT3D /language "en-US"`, from the Start-menu shortcut) verified read-only. **Still open (needs a live Plant 3D session):** with the plug-in installed, start Plant 3D and confirm the launch args, the main-window title, the start screen (does it reopen a last or sample project?), the load prompt(s), the default new document and its title, whether the plug-in tab is in the UI tree, and the Snapshot size | `hosts/autocad-plant3d.md` filled in (front matter + sections); one raw Snapshot saved as `tests/fixtures/` |
| 2 | Models: LOAD, `window_in_ui`, `seen_in_ui`, NEEDS_REVIEW, entry-point card | **Done.** Strict-schema test passes; YAML round trip |
| 3 | UI-tree parser + verdict (`window_in_ui`, `seen_in_ui`, NEEDS_REVIEW) | **Done** on a real Programs-and-Features Snapshot plus a made-up host tree in the same format (replace with the step-1 Plant 3D Snapshot). Found: Windows-MCP sometimes returns the Snapshot text as a JSON list of strings; the parser decodes it |
| 4 | Self-check LOAD rules, built-in LOAD-000, `understanding.md` card | **Done.** Unit tests per rule |
| 5 | Recorder: raw Snapshot text per call; `record_observation` Snapshot rule | **Done** (the rule applies to executed records only, so "install failed" can still be recorded) |
| 6 | Skills: test-design LOAD section, `host-interaction.md` | **Written**; team review open. `test_skills` checks front matter and that generic files name no product |
| 7 | `host.py`, preflight check, guardrail changes, App-under-test block, `finally` kill, 40 min limit | **Done.** A local `CodeBase/.env` with `AGENT2_TIMEOUT_MIN=20` still overrides the new default |
| 8 | Report: NEEDS_REVIEW, screenshots and "Agent 2 said" with LOAD | **Done** |
| 9 | Live run (elevated F5) | **Done**: see §10 |
| 10 | Docs | **Done:** ARCHITECTURE.md v2.3 (D40–D52), ADR.md (ADR-033–036), AGENT_TOOLING_REVIEW.md |

---

## 7. Verification (Phase 1)

1. **Unit:** `uv run pytest` covers the parser, both new checks, NEEDS_REVIEW, the self-check rules, LOAD-000, the recorder, `host.py`, the preflight check and the guardrails. No API calls.
2. **Design only:** Agent 1 on the P&ID Exporter produces an entry-point card with kind `ribbon_tab`, label "P&ID Exporter", items `[Export]` and use_context "in a P&ID project and have a drawing open", each cited. It also adds an open question about the second, unnamed button. It writes one LOAD-001 that passes the self-check, and code adds LOAD-000.
3. **Live (elevated F5):**
   - LOAD-000 PASS: the host window and a new document are in the UI tree, with no error dialog; any accepted load prompt is shown in the report;
   - LOAD-001 PASS if an element named "P&ID Exporter" is in the host window's UI tree, otherwise NEEDS_REVIEW with the screenshot;
   - the host is killed by Agent 2 (or by code); UNIN PASS; nothing is left installed.
4. **Failure paths:**
   - host already running → STOPPED at preflight, nothing installed;
   - install fails → LOAD BLOCKED, host not started, UNIN still runs;
   - host won't start → LOAD-000 FAIL/ERROR, LOAD-001 BLOCKED, UNIN PASS;
   - unknown dialog → screenshot + LOAD ERROR, host killed;
   - Agent 2 tries `msiexec /x` with the host running → rejected, then it kills the host;
   - Agent 2 times out → `finally` kills the host, then cleanup uninstalls.

---

## 8. Risks (Phase 1)

| Risk | Mitigation |
|---|---|
| The plug-in's ribbon tab isn't in the UI tree | NEEDS_REVIEW with the screenshot (L4). Fix the observation (e.g. a host-notes recipe that exposes it) instead of weakening rules (§9 open point) |
| Plant 3D reopens the last or sample project at start | Seen in step 1; if it happens, write the start steps (or a launch arg) into host notes. LOAD still uses only the default new document |
| The tab appears only in a specific workspace | Seen in step 1; written into host notes under *Where app entry points appear* |
| Slow host start, start page | `WaitFor` on the main window, 105 s × 2; 40 min total |
| A weak model wanders in the host UI | Short fixed skill; `App` only `launch_executable` with the exact path and args; code-decided checks; Snapshot required before record; repeat limit (D36) |
| Load or trust prompts; licence or entitlement dialogs (`EntitlementApiWrapper.dll`) | Generic rule (L10): one-time yes only for the app under test; anything else → screenshot, LOAD ERROR, host killed |
| Snapshot text over 20,000 characters | The verdict reads the raw files (L17); a filter for the model's view only if step 1 shows it's needed |
| Killing the user's own host session | Preflight stops if the host runs; code kills only PIDs started during the run (L12) |
| The host is left running if the run is killed | `finally` kills it; killing F5 itself is covered by D39 |

---

## 9. Phase 1b: UI claims judged by an LLM, leftovers, covered UI, generic skills (agreed and built 2026-10-14)

### 9.1 Why
Run `20261014-124157` (11 PASS, 1 NEEDS_REVIEW) showed the limits of checking UI claims by exact strings:
- **The documents and the product disagree.** The user guide says *"a new tab called 'P&ID Exporter', which contains two new buttons"*. The plug-in shows a tab **"P&ID Connector"** with two groups: **Tools** (Export P&ID, Export selection) and **Settings** (Help, Language, Info). The plug-in's own DLLs contain exactly these words (checked by extracting the MSI with 7-Zip); "P&ID Exporter" is not the tab name anywhere.
- **Whether a UI claim holds is a judgement** (same entry point, different name? how many "buttons"?), not a string comparison.
- **Plant 3D doesn't expose ribbon tabs in the UI tree**, so `seen_in_ui` could only say NEEDS_REVIEW.
- Code and skills that "select the tab, open its groups" would only fit ribbon hosts and **break the generic design (D1)**.

### 9.2 Decisions
| # | Topic | Decision |
|---|---|---|
| L20 | Who decides UI claims | An **LLM judge**: a separate model call with a fresh context that sees only the claim and the evidence, using the same `OPENAI_MODEL`. Agent 2 does not grade its own work (it is the executor; its context is long; earlier runs invented values). **Facts stay with code** (D7): exit codes, registry, files, and LOAD-000's host window / new document (`window_in_ui`). |
| L21 | Claims, not strings | New check **`judged`**: its `value` is the documented claim in plain words; the test's citation(s) give the source. Agent 1 writes **LOAD-001** "the documented entry point is present" and **LOAD-002** "the documented items of the entry point are reachable" (when the documents name or count items). `seen_in_ui` is retired. Nothing in the claim format is specific to tabs: it is whatever the documents say (tab, menu, toolbar, palette, window). |
| L22 | The app's own UI text as evidence | S1 (code, no UI) extracts the readable text of the binaries in the installer (`.dll`, `.exe`: UTF-16 and UTF-8 strings, filtered, de-duplicated, capped) into a new citable source **`U1`**, marked as *hints*: it can contain text of related products (here: the Revit Importer). Agent 1 may cite `U1` next to the documents, and must raise an open question when they disagree. Generic for any Windows app. |
| L23 | The judge's rule | Shown entry point/items **match the documents** → PASS. **Match only the app's own text (`U1`)** → **PASS with a finding** "documentation mismatch: the documents say X, the app shows Y". **Match neither** → FAIL. **Can't tell from the evidence** → NEEDS_REVIEW. |
| L24 | Agent 2 explores generically | Skill wording without UI types: bring the host to the state the claim describes, then explore the entry point like a tester. **Open things that only reveal more UI** (e.g. a tab, a group, a drop-down, a menu), **never trigger anything that acts** (runs a feature, opens a website or window, changes settings, saves). A Screenshot of every state; the notes describe what was seen. The evidence and record are the existing ones (screenshots attached, `notes`), as for dialogs (D56). |
| L25 | Code guards around the judge | The judge must name at least one screenshot that is attached to that test, otherwise ERROR. No screenshots → ERROR (never judged from notes alone). A failed judge call → ERROR for that test, not a crash. Preconditions and BLOCKED as today. Text in screenshots and notes is untrusted data for the judge. The judgement (verdict, what is shown, differences, findings, screenshot used, reason) is stored in `results.json`. |
| L26 | Report | For every judged test: the claim with its quote, the verdict, the judge's reason, the findings and the screenshot it used. A **Findings** section lists all findings of the run (e.g. documentation mismatches). |
| L27 | Nothing left behind *(added after run 20261014-153924)* | Built-in **UNIN-000**, decided by code: footprint before the install vs after the uninstall. Program leftovers → FAIL; user settings → PASS with a finding; never deleted (ARCHITECTURE.md D64). The run found the plug-in's leftovers `HKCU\Software\PidConnectorExport`, `%LocalAppData%\PidConnectorExport\license.dat` and a .NET `user.config` (language `en-US`, default `de-DE`). |
| L28 | Covered UI *(added after run 20261014-153924)* | Agent 2 uncovers the claimed UI with view-only, undone changes and checks its screenshots show every named element; the judge: hidden is not missing (NEEDS_REVIEW). A clean host profile per run is deferred (D65). Also fixed: the judge's closed event loop (D66); re-judging that run's screenshots gave LOAD-001 and LOAD-002 PASS with documentation-mismatch findings. |
| L29 | Generic skills *(experiment 2026-10-14)* | All host- and app-specific prose removed from the skills; the host profile is front matter only (`host_process`, `releases`). Run 20261014-175347 gave the same 14 PASS and findings as 20261014-162644, faster (ARCHITECTURE.md D67). §4.2's "standard sections" are superseded: hosts have no prose sections any more. |

### 9.3 Design
- **Agent 1 (test-design skill):** the entry-point card stays (`kind`, `label`, `items`, `use_context`, `sources`), and its sources may now include `U1`. LOAD-001 claim: e.g. *"After installation the host shows a new tab called 'P&ID Exporter'"* (D2). LOAD-002 claim: e.g. *"The entry point contains two new buttons; one is 'Export', which exports the drawing to JSON"* (D2). Open questions: e.g. *"D2 says 'P&ID Exporter'; U1 contains 'P&ID Connector'"*.
- **S1 (`design/static_read.py` + a new `design/ui_text.py`):** UI-text extraction into `documents/U1_ui_text.txt`, added to the evidence pack.
- **Agent 2 (`host-interaction.md`):** the exploration rule of L24. LOAD-001 and LOAD-002 are recorded with screenshots and notes; their values are Agent 2's description only.
- **Judge (`execute/judge.py` + `skills/execute/judge.md`, both generic):** one call per `judged` test after Agent 2, inside the verdict step. Input: the claim, its quotes (documents and `U1`), the test's screenshots (as images, the latest few), the host-window part of its Snapshot texts, and Agent 2's notes, labelled as *the executor's description, not proof*. Output, strict schema: `verdict`, `shown`, `differences`, `findings[]`, `evidence[]`, `reason`.
- **Verdict engine:** `judged` expectations call the judge; L25 guards; the precedence stays BLOCKED → ERROR → FAIL → NEEDS_REVIEW → PASS.
- **Models:** `Check` + `judged`, − `seen_in_ui`; new `Judgement`; `TestResult` + `judgement`, `findings`.

### 9.4 Changes by file (in `CodeBase/`)
| File | Change |
|---|---|
| `src/mpagent/design/ui_text.py` (new), `static_read.py`, `evidence.py` | Extract the app's UI text → source `U1` |
| `skills/test-design/SKILL.md` | `judged` claims; LOAD-001 + LOAD-002; citing `U1`; mismatch → open question |
| `src/mpagent/design/selfcheck.py` | Rules for `judged` (LOAD only, citation required, claim must be supported by its quotes); LOAD-002 when items are documented; `seen_in_ui` rejected |
| `skills/execute/host-interaction.md` | Generic exploration (reveal vs act), screenshots and notes |
| `src/mpagent/execute/judge.py`, `skills/execute/judge.md` (new) | The judge call and its instructions (generic) |
| `src/mpagent/execute/verdict.py`, `report.py`, `templates/report.html.j2` | Judged checks, guards, judgement and findings in results and report |
| `src/mpagent/models.py` | `Check.JUDGED`, `Judgement`, `TestResult.judgement/findings`; remove `SEEN_IN_UI` |
| `tests/` | `test_ui_text`, `test_judge` (stand-in model), extend `test_selfcheck`, `test_verdict`, `test_skills` |

### 9.5 Build steps
| # | Step | Done when |
|---|---|---|
| 1 | `U1` UI-text extraction in S1 | **Done.** `U1` = 12,650 characters with "P&ID Connector", "Tools", "Export selection", "Settings", "Language", "Help", "Info"; binaries deleted after reading. Also fixed: S1 called Git's `expand.exe` when Git's tools were on PATH (so nothing unpacked in tests); it now always uses Windows' own |
| 2 | Models + self-check for `judged`, LOAD-002 | **Done.** Unit tests per rule |
| 3 | Judge (`judge.py`, `judge.md`) with a stand-in model for tests | **Done.** Unit tests: guards, ERROR paths, the judge's input |
| 4 | **Offline replay** on run `20261014-124157`: the judge gets screenshot 028 and the notes | **Done, twice, same result:** LOAD-001 PASS, finding *"Documentation mismatch: the documents say 'P&ID Exporter', the app shows 'P&ID Connector'"*, evidence `028_Screenshot_1.png`; the replayed run = 12 PASS |
| 5 | Skills: test-design, host-interaction (L24) | **Written**; team review open |
| 6 | Report: judgements and the Findings section (+ `FINDING` lines in `run.log`) | **Done** |
| 7 | Live run (elevated F5) | **Done**: see §10 |

### 9.6 Risks
| Risk | Mitigation |
|---|---|
| The judge hallucinates | It must name an attached screenshot (L25); its reason is stored and shown; "can't tell" is allowed (NEEDS_REVIEW); it never judges from notes alone |
| Different verdicts on repeated runs | Strict output schema; the rule of L23 in the judge skill; the screenshots stay as evidence for a human |
| `U1` noise (shared DLLs, libraries) | Marked as hints; only cited strings count; filtering and a size cap |
| Text in screenshots tries to instruct the judge | Untrusted-data rule in the judge skill, as for Agent 1 and Agent 2 |
| Cost and time | One judge call per judged test (two per run here) |

## 10. Live runs and results

| Run | Skills | Result | What it showed |
|---|---|---|---|
| 20261014-111858 | case-tuned | 10 PASS, 1 FAIL, 1 BLOCKED | the blanket "stop at any other dialog" rule failed LOAD-000 on the plug-in's harmless notice → dialogs decided by Agent 2 (L10, D56) |
| 20261014-124157 | case-tuned | 11 PASS, 1 NEEDS_REVIEW | ribbon tabs aren't in the UI tree; the documents name the tab "P&ID Exporter", the app shows "P&ID Connector" → LLM judge and U1 (Phase 1b) |
| 20261014-153924 | case-tuned | 11 PASS, 1 ERROR, 1 BLOCKED | the judge's closed event loop (fixed, D66); the plug-in's leftovers found by hand → UNIN-000 (L27) |
| 20261014-162644 | case-tuned | **14 PASS** | first fully green run, three documentation-mismatch findings |
| 20261014-175347 | **generic** | **14 PASS** | same verdicts and findings without any host or app knowledge in the skills, faster (L29, D67) |
| 20261014-194215 | **generic**, clean machine | **14 PASS** | German plug-in UI handled without hints; UNIN-000 reported the plug-in's three user-settings leftovers |

**Open points for LOAD (none blocking):**
- the judge could name "the app's UI is in another language than the host's" more explicitly;
- the same documentation finding appears under LOAD-001 and LOAD-002 (the report could show it once);
- a clean host profile per run (palettes, last template) stays deferred (D65).

**FUNC (running features):** planned in [`FUNC_TESTS_PLAN.md`](FUNC_TESTS_PLAN.md) (decisions F1–F16, for a grill-me review). The open point from Q6 (a NEEDS_REVIEW on LOAD-001 must not block FUNC) is answered there by F8: FUNC depends on LOAD-000 only.
