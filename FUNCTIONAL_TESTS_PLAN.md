# Implementation Plan: LOAD test (is the plug-in loaded in its host?), then FUNC

> **Status:** v3, after the grill-me review on 2026-10-13 (questions Q1–Q17, all agreed). Branch `Dev-FunctionalTest`. **Code implemented 2026-10-13** (build steps 2–8 and 10 done, see §6). Recorded in ARCHITECTURE.md v2.3 as **D40–D57** and in ADR.md as ADR-033–040 (D53–D57 / L19 added after the live runs of 2026-10-13/14).
> **Builds on:** [`ARCHITECTURE.md`](ARCHITECTURE.md) v2.2 (D1–D39), [`ADR.md`](ADR.md). The decisions in §3 go into ARCHITECTURE.md as D40+ and into ADR.md.
> **v3 changes:** LOAD opens the host's **default new document** (not an app-specific one). Code adds a **built-in LOAD-000**, and Agent 1 writes **at most one** LOAD test. Code decides from the **raw UI tree** (`window_in_ui`, `seen_in_ui`). There is **one** Agent 2 session, protected by a "no uninstall while the host runs" guardrail. Host facts that code needs go in **YAML front matter** in the host notes. The host is **closed by Process kill**, and **preflight stops if the host is already running**. The **machine check is now build step 1**.
> **Rule kept from D1:** nothing in the core code or the generic skills names Plant 3D, P&ID, a ribbon label or any plug-in. Product knowledge lives only in **host notes** (one Markdown file per host) and comes from the **app's own documents** at run time. P&ID examples appear only in tests and in `hosts/autocad-plant3d.md`.

---

## 1. Goal (Phase 1)

Today a run tests **ENV → INST → UNIN**. Phase 1 adds one category, **LOAD**, between install and uninstall:

```
ENV → INST → LOAD (start host → default new document → Snapshot → entry point in the UI tree) → kill host → UNIN
```

| LOAD test | Written by | Decided by | Example for the P&ID Connector Exporter |
|---|---|---|---|
| **LOAD-000** host ready with a new document | **code** (built-in, like ENV-000) | code: `window_in_ui` on the raw UI tree; Agent 2's report for dialogs | Plant 3D's main window, with a `Drawing1` document in it |
| **LOAD-001** entry point visible | **Agent 1**, cited from the app's docs | code: `seen_in_ui` on the raw UI tree | UserGuide: *a new tab called "P&ID Exporter"* → an element named `P&ID Exporter` inside the host window |

**What makes it generic:** Agent 1 reads only *app* facts from the app's documents: the entry point and its label. *Host* facts (how to start the host, its window titles, its processes, how to open a new document) come from **host notes**. Code reads those facts from the host notes' front matter. A different app on the same host changes only the documents; a different host only adds one host-notes file.

**Demo acceptance (Phase 1):** one F5 run on the P&ID Exporter gives LOAD-000 PASS and LOAD-001 PASS (or NEEDS_REVIEW with a screenshot), the host is killed again, and UNIN still runs and passes.

**Out of scope for Phase 1:** app-specific documents (e.g. a P&ID drawing in a project), sample projects or existing files, clicking the app's tab or buttons, running its features (Export), checking output files, closing the host through its UI, a second host.

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

## 3. Decisions (agreed in the grill-me session, 2026-10-13)

| # | Question | Decision |
|---|---|---|
| L1 (Q1) | What does LOAD open? | The host + its **default new document** (a host-notes recipe, e.g. Ctrl+N → `Drawing1`). The app-specific context ("in a P&ID project with a drawing open") is about *using* the app: Agent 1 records it on the card as `use_context` for **Phase 2**. |
| L2 (Q2) | Who writes the LOAD tests? | **Code adds a built-in LOAD-000** (`origin: built-in`, no citation) whenever the host notes have `host_process`. **Agent 1 writes at most one test, LOAD-001** (the app claim, cited). *(After run 20261013-172934: exactly one is required when the entry point is visible.)* If the docs name no visible entry point, there is no LOAD-001 and Agent 1 adds an open question. |
| L3 (Q3) | What does LOAD-001 check? | **The label only** (e.g. the tab name). `entry_point.items` lists only **quoted** names. Anything the docs count but don't name becomes an open question. Clicking the tab or buttons is Phase 2. |
| L4 (Q4) | How does `seen_in_ui` match? | Code parses the **UI Tree** section, takes the subtree of `window "<title>"` whose title matches the host's `main_window` regex, and passes only if an **element's quoted name equals the label** after normalising (casefold, collapsed whitespace, `&`/`&&` accelerator markers stripped). No host window → ERROR. Host window present but no such element → **NEEDS_REVIEW** if a screenshot exists, otherwise **FAIL**. |
| L5 (Q5) | Agent 2's value vs the UI tree | For `seen_in_ui` and `window_in_ui`, **the UI tree decides**. The "null value → ERROR" rule doesn't apply, and Agent 2's value is shown in the report only ("Agent 2 said: …"). **`record_observation` refuses** a test with such a check if no Snapshot was taken since the previous record ("take a Snapshot of the host window first"). |
| L6 (Q6) | NEEDS_REVIEW | New status. Precedence within a test: BLOCKED → ERROR → FAIL → NEEDS_REVIEW → PASS. It **isn't PASS**, so dependents are BLOCKED. Shown in `results.json` counts, `summary_line` and the report (its own colour, screenshot inline). Exit codes are unchanged. **Don't design around it now** (see §9 open point). |
| L7 (Q7) | One or two Agent 2 sessions? | **One session.** A guardrail **rejects an uninstall `msiexec /x` while any host process is running**, telling Agent 2 to kill the host first. `finally` kills the host again as a backstop. No env hand-over, one `CallPolicy`. |
| L8 | Does UNIN depend on LOAD? | **No**, only on INST. The uninstall is always tested. |
| L9 (Q8) | Host facts for code; which programs Agent 2 may start | Each host-notes file gets **YAML front matter `host_process`** (§4.2). Code resolves the executable and passes the **exact path + args** in the App-under-test block. The guardrail allows `App` only as `launch_executable` with **exactly that path and those args**. `switch`/`resize` stay allowed; `launch` by name is rejected. `none.md` has no `host_process`, so there is no LOAD. |
| L10 (Q9) | Dialogs at host start | *(Updated 2026-10-14, ARCHITECTURE.md D56.)* **Agent 2 decides** how to handle each dialog, as a careful tester would: read it, screenshot it, judge what it is (notice, load/trust prompt for the app, error while the host still works, crash, lasting change or unclear) and choose the button with the smallest lasting effect so the test continues. Never "Always …", "Don't show again" or a settings change. Evidence = the attached screenshots; the record = the LOAD test's `notes`. *Was:* one-time yes for load prompts and "any other dialog stops LOAD", which failed LOAD-000 on the plug-in's harmless German notice "Hinweis" (run 20261014-111858). |
| L11 (Q10) | Who decides LOAD-000? | New check **`window_in_ui`**: a window or document/tab title matching a regex exists in the host window subtree (same parser as `seen_in_ui`). `host_started` uses `main_window`, and `document_opened` uses `new_document` (from host notes). Not found → FAIL. `error_dialog_seen` and `load_prompt_seen` stay Agent 2's report. |
| L12 (Q11) | Host already running at start | **Preflight stops**: "<host> is running (PIDs …). Close it and run again — Agent 2 not started." *(As built: since the preflight guarantees that no host process ran before, code kills every host process it finds later; no PID list is kept.)* `finally` order: **kill host → cleanup (msiexec /x) → verdicts → report**. |
| L13 (Q12) | How the host is closed | **Agent 2: one `Process kill`** of the host's processes after recording LOAD (never save, never use the host's own exit). **Code: kill only**, no graceful attempt (it would hang on "Save changes?"). The *Close without saving* host-notes section is kept for Phase 2. |
| L14 (Q13) | Waiting and time limits | The guardrail **caps `WaitFor.timeout` and `Wait.duration` at tool timeout − 15 s (105 s)** with the hint "call again to wait longer". The skill waits for the host window at most **twice** (≈ 3.5 min). `AGENT2_TIMEOUT_MIN` = **40** (shrink after real timings), `AGENT2_MAX_TURNS` stays 150. |
| L15 (Q14) | Which entry-point kinds get LOAD-001 | Only **`ribbon_tab`, `menu`, `toolbar`** (visible after start). For `command` or `own_window`, Agent 1 fills the card but writes no LOAD-001 and adds an open question. `Summary.entry_point` is nullable. |
| L16 (Q15) | LOAD-000's precondition; failed install | LOAD-000 depends on **the INST test(s) observing `install_exit_code`** (D24 guarantees one exists). LOAD-001 depends on LOAD-000. If the recorded install exit code isn't a success value, Agent 2 **doesn't start the host**: it records LOAD as `executed: false` ("install failed") and goes on to UNIN (verdict: BLOCKED). |
| L17 (Q16) | Which Snapshot text the verdict reads | The recorder saves the **full raw text** of every Snapshot as `evidence/<n>_Snapshot_ui.txt`. `window_in_ui`/`seen_in_ui` read **only those files**, never the trace (capped at 20,000 characters) or the model's cleaned copy. What the model sees is unchanged in Phase 1. |
| L18 (Q17) | Build order | **The machine check is build step 1**: it fills the Plant 3D host notes and saves a real Snapshot that becomes the parser's test fixture. |
| L19 | Test-case review before execution | *(2026-10-14, requested by the seniors; ARCHITECTURE.md D57.)* After Agent 1 writes `testcases.yaml`, the console lists the tests and asks **"Go ahead and run them on this machine? [y/n]"**. `n` stops the run before the preflight, so nothing is installed. Without a console the run continues. |

---

## 4. Design (Phase 1)

### 4.1 Agent 1: entry-point card and LOAD-001 (generic)
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

### 4.2 Host notes: front matter + standard sections
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

### 4.3 Agent 2: host interaction (new generic skill)
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
| 1 | **Machine check (manual, ~30 min). Partly done:** registry lookup (`ACAD-A117:409`, `AcadLocation`) and launch args (`/product PLNT3D /language "en-US"`, from the Start-menu shortcut) verified read-only. **Still open (needs a live Plant 3D session):** with the plug-in installed, start Plant 3D and confirm the launch args, the main-window title, the start screen (does it reopen a last or sample project?), the load prompt(s), the default new document and its title, whether the plug-in tab is in the UI tree, and the Snapshot size | `hosts/autocad-plant3d.md` filled in (front matter + sections); one raw Snapshot saved as `tests/fixtures/` |
| 2 | Models: LOAD, `window_in_ui`, `seen_in_ui`, NEEDS_REVIEW, entry-point card | **Done.** Strict-schema test passes; YAML round trip |
| 3 | UI-tree parser + verdict (`window_in_ui`, `seen_in_ui`, NEEDS_REVIEW) | **Done** on a real Programs-and-Features Snapshot plus a made-up host tree in the same format (replace with the step-1 Plant 3D Snapshot). Found: Windows-MCP sometimes returns the Snapshot text as a JSON list of strings; the parser decodes it |
| 4 | Self-check LOAD rules, built-in LOAD-000, `understanding.md` card | **Done.** Unit tests per rule |
| 5 | Recorder: raw Snapshot text per call; `record_observation` Snapshot rule | **Done** (the rule applies to executed records only, so "install failed" can still be recorded) |
| 6 | Skills: test-design LOAD section, `host-interaction.md` | **Written**; team review open. `test_skills` checks front matter and that generic files name no product |
| 7 | `host.py`, preflight check, guardrail changes, App-under-test block, `finally` kill, 40 min limit | **Done.** A local `CodeBase/.env` with `AGENT2_TIMEOUT_MIN=20` still overrides the new default |
| 8 | Report: NEEDS_REVIEW, screenshots and "Agent 2 said" with LOAD | **Done** |
| 9 | Live run (elevated F5) | §7 acceptance |
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

## 9. Phase 2 (later): running features (FUNC)

**Open point from the grill (Q6):** NEEDS_REVIEW on LOAD-001 would block every FUNC test that depends on it. If step 1 or the live runs show that the entry point isn't in the UI tree, **fix the observation** (e.g. a host-notes recipe that makes it visible), don't weaken the precondition rule.

Kept from plan v1, to be grilled separately once Phase 1 works:
- **Feature cards** for each documented feature (entry point, `use_context`, data kind, result, automatable yes/no). Only safe features become tests, max 3.
- **App-specific context:** opening `use_context` documents (e.g. a P&ID drawing inside a project).
- **Clicking the app's entry point:** select the tab, check the quoted `items` (e.g. `Export`).
- **Test-data catalogue** (`test_data/catalogue.yaml`) of approved sample files, e.g. host-shipped sample projects; **code copies** them into `run/sandbox/` before Agent 2.
- **File checks by code** (`file_exists`, `file_not_empty`, `json_valid`, `xml_valid`, `file_contains`) on outputs saved under `evidence\output\`.
- **Clean host exit** ("the host exits with the app loaded, without errors") using the host notes' *Close without saving*.
- Optional **host command channels** (startup script, COM) from host notes, instead of clicking.
- Example for the P&ID Exporter: Export on a P&ID drawing writes valid, non-empty JSON; content correctness = NEEDS_REVIEW.
