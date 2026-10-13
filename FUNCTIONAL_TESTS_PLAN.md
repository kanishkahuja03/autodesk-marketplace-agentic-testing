# Implementation Plan: LOAD test (is the plug-in loaded in its host?), then FUNC

> **Status:** draft v2 for a grill-me review, 2026-10-13. Branch `Dev-FunctionalTest`.
> **Builds on:** [`ARCHITECTURE.md`](ARCHITECTURE.md) v2.2 (D1–D39), [`ADR.md`](ADR.md). Once agreed, the decisions in §3 go into ARCHITECTURE.md as D40+ and into ADR.md.
> **v2 change:** Phase 1 is now **only the load check**. Agent 1 and Agent 2 work out from the app's documents how to open the host, which (new, empty) document the app needs, and what extra UI entry point should appear, then check it with a screenshot. Sample projects, the data catalogue and running features (e.g. Export) move to **Phase 2** (§9).
> **Rule kept from D1:** nothing in the core or the generic skills names Plant 3D or any plug-in. Product knowledge lives only in **host notes** (one Markdown file per host) and comes from the **app's own documents** at run time.

---

## 1. Goal (Phase 1)

Today a run tests **ENV → INST → UNIN**. Phase 1 adds one category, **LOAD**, between install and uninstall:

```
ENV → INST → LOAD (start host → new document of the needed kind → find the app's entry point → screenshot) → close host → UNIN
```

| LOAD checks (generic) | Example: what Agent 1 should derive for the P&ID Connector Exporter |
|---|---|
| The host starts with the app installed, and no error dialog appears | AutoCAD Plant 3D starts |
| A **new, empty document of the kind the app needs** is open (no sample project, no existing file) | The user guide says "be in a P&ID project and have a drawing open", so: a new P&ID drawing |
| The app's **entry point** described in its documents is visible in the host UI | The user guide says "a new tab called P&ID Exporter … two new buttons", so: a ribbon tab "P&ID Exporter" with "Export" and "Info" |
| A screenshot of that state is saved as evidence | `evidence/…png` showing the tab |

**What makes it generic:** Agent 1 reads the entry point and the needed document kind **from the app's documents** (cited, quote-checked). *How* to start the host, create a new document of a kind, and close it comes from **host notes**. Agent 2 follows generic skills plus those notes. A different app on the same host only changes the documents; a different host only adds one host-notes file.

**Demo acceptance (Phase 1):** one F5 run on the P&ID Exporter gives LOAD results with a screenshot showing the extra ribbon tab, the host is closed again, and UNIN still runs and passes.

**Out of scope for Phase 1:** opening sample projects or existing files, clicking the app's buttons or running its features (Export, Info), checking output files, a second host.

---

## 2. Background and research summary (unchanged findings)

- **No ready-made tool writes functional tests for desktop plug-ins.** [Playwright's planner/generator/healer agents](https://playwright.dev/docs/test-agents) are web-only; our Agent 1 (planner) and Agent 2 (executor) already follow that pattern.
- **Host command channels** (e.g. AutoCAD startup scripts or COM `SendCommand`) can be more reliable than clicking, but they're host-specific, so they belong in host notes (Phase 2 option).
- **Oracles derived from docs hallucinate** ([survey](https://www.themoonlight.io/review/test-oracle-automation-in-the-era-of-llms)), so the verdict must rest on **facts code can check** (here: the entry point's text in the UI tree), with a screenshot for humans.
- **On this machine:** Plant 3D 2027 is installed (`AcadLocation` in the registry); the plug-in's manifest lists **no commands** and loads at startup, so its ribbon tab is the visible entry point.
- **Lessons from the live runs (2026-10-13):** a weak model (gpt-4o-mini) goes wrong whenever it has free rein in the UI (Win+R, guessed coordinates, wrong list row). So the UI steps must be **short, fixed in a generic skill, and backed by code checks**, and never touch anything except the host window.

---

## 3. Decisions to grill (each with a recommendation)

| # | Question | Options | Recommendation |
|---|---|---|---|
| L1 | What does the LOAD test open? | (a) the host + a **new, empty document of the kind the docs require** · (b) the host only · (c) a sample project | **(a)**: some entry points only appear (or only work) with the right document open; a new document needs no test data |
| L2 | Where does "which document kind" and "which entry point" come from? | (a) **Agent 1, from the app's docs**, cited and quote-checked · (b) host notes · (c) Agent 2 discovers it on screen | **(a)**: it's app knowledge, and citations keep it honest |
| L3 | Where does "how to start the host / create a new document of kind X / close it" come from? | (a) **host notes**, with standard sections · (b) Agent 2 figures it out | **(a)**: host knowledge, written once per host, verified on the machine |
| L4 | Who decides "entry point visible"? | (a) **code**: a new check `seen_in_ui` searches the UI-tree text of the Snapshots taken during that test for the expected label · (b) Agent 2 reports true/false · (c) a human looks at the screenshot | **(a)**, with the screenshot as evidence. If the label is not in the UI tree (some ribbons aren't exposed), the result is **NEEDS_REVIEW**, not PASS |
| L5 | New status NEEDS_REVIEW now? | (a) yes, for "only a screenshot could show it" · (b) no, FAIL instead | **(a)**: it's honest, and the report shows the screenshot |
| L6 | Who closes the host before UNIN? | (a) Agent 2 closes it without saving; **code makes sure** (graceful, then kill) before UNIN · (b) Agent 2 only | **(a)**: an uninstall with the host still running can need a reboot or fail |
| L7 | How is "code makes sure before UNIN" possible inside one Agent 2 session? | (a) **split Agent 2 into two sessions**: session A = ENV + INST + LOAD, then code closes the host, session B = UNIN · (b) keep one session and close the host only in `finally` | **(a)**: deterministic host close, and smaller, more focused sessions for the weak model (a first step toward "one test at a time") |
| L8 | Does UNIN depend on LOAD? | (a) no, only on INST · (b) yes | **(a)**: the uninstall is always tested and cleaned up |
| L9 | Which programs may Agent 2 start? | (a) only the **host executable**, resolved from the registry (host notes) and passed by code · (b) anything via the App tool | **(a)**: a guardrail rejects other executables (no Run dialog, no Control Panel) |
| L10 | Time limits | keep 20 min · raise | **Raise to 40 min**, and allow up to 3 min for the host to become ready |
| L11 | How many LOAD tests? | (a) **3 fixed shapes** (host started cleanly · new document open · entry point visible), cited · (b) free | **(a)**, with fixed key names so code can check them (like D24) |

---

## 4. Design (Phase 1)

### 4.1 Agent 1: entry point and context from the docs (generic)
The test-design skill gets a LOAD section. Agent 1 fills one **entry-point card** in `summary` (shown in `understanding.md`), every field cited:

| Field | Meaning | Example (derived, not hard-coded) |
|---|---|---|
| `entry_point.kind` | `ribbon_tab` · `menu` · `toolbar` · `command` · `own_window` | `ribbon_tab` |
| `entry_point.label` | the exact text the UI should show | `P&ID Exporter` |
| `entry_point.items` | buttons or commands inside it, if documented | `Export`, `Info` |
| `context.document_kind` | the kind of document that must be open, or `none` | `P&ID drawing` |
| `context.how_documented` | the citation | D2: "the user must be in a P&ID project and have a drawing open" |

Then it writes **three LOAD tests** (L11), with these keys:

| Test | Observes | Expected | Preconditions |
|---|---|---|---|
| LOAD-001 host starts cleanly | `host_started`, `error_dialog_seen` | `exists`, `not_exists` | INST test(s) |
| LOAD-002 new document open | `document_opened` (+ `document_kind`) | `exists` | LOAD-001 |
| LOAD-003 entry point visible | `entry_point_label` | `seen_in_ui` with `value` = the label | LOAD-002 (or LOAD-001 if `document_kind` is `none`) |

If the documents don't name an entry point, Agent 1 writes no LOAD-003 and adds an open question. Self-check (new rules):
- LOAD tests depend on an INST test;
- UNIN tests don't depend on LOAD (L8);
- `seen_in_ui` values must be quoted from a source;
- at most these three LOAD tests.

### 4.2 Host notes: standard sections (generic structure)
Every `skills/hosts/<id>.md` gets the same headings, filled in per host and verified on the machine:
- **Start:** how to find the executable (e.g. a registry value) and its arguments;
- **Ready signal:** the window title or element that shows the host is ready;
- **Known popups:** start page, security or trust dialogs, what to answer (never anything that changes settings permanently);
- **Create a new document of a kind:** per document kind, the steps (e.g. a template or a "New" command), and the expected window or tab title;
- **Where app entry points appear:** e.g. "plug-in ribbon tabs appear next to the built-in tabs; their names are in the UI tree";
- **Close without saving:** the steps, and the "don't save" answer;
- **Processes:** names (e.g. for the code close step).

Plant 3D items to **verify** in build step 6: the launch arguments for Plant 3D, the start page, how to create a new P&ID drawing without opening a sample project (and whether P&ID needs a project context at all), how the plug-in's ribbon tab shows in the UI tree, how to close without saving.

### 4.3 Agent 2: host interaction (new generic skill)
`skills/execute/host-interaction.md` (generic, no product names):
1. Start the host with the App tool using the **executable path given in the input** (L9). Wait for the ready signal (up to 3 min). Handle known popups from the host notes; an unknown dialog → screenshot, record, stop the LOAD tests.
2. Create a **new document of the kind given in the test** using the host notes' steps. Wait for its window or tab.
3. `Snapshot` the host window. Look for the entry point **label** (and items) in the UI tree. If it sits on a tab, it's enough that the tab label is visible; don't click the app's buttons in Phase 1. Take a `Screenshot`.
4. Record each LOAD test with raw facts (e.g. `entry_point_label` = the text found, or `null`).
5. **Close the host without saving** (host notes).

The UI rules from the installer skill still apply: full paths only, no Run dialog, no guessed coordinates, never touch the console, stop after two failed attempts.

### 4.4 Code support (all generic)
- **Snapshot text per test:** the call recorder keeps the UI-tree text of every Snapshot since the last `record_observation` (like the screenshots, D31) and attaches it to that observation as evidence (`evidence/<n>_Snapshot_ui.txt`).
- **`seen_in_ui` check:** the verdict engine searches those texts for the expected label (case and whitespace insensitive). Found → PASS. Not found but a screenshot exists → **NEEDS_REVIEW** (L4, L5). No snapshot at all → ERROR.
- **Host executable:** code reads it the way the host notes say (for AutoCAD-family hosts, the registry value) and passes it in the "App under test" block (D38). The guardrail allows the App tool to start only that executable (L9).
- **Close the host (L6, L7):** `execute/host.py` closes the host's processes from the host notes (graceful first, then kill). Code runs it between Agent 2 session A and session B, and again in `finally`.
- **Guardrail:** `Process kill` is also allowed for the host's processes.

### 4.5 Pipeline order (Phase 1)
```
… preflight → Agent 2 session A (ENV, INST, LOAD) → code closes the host → Agent 2 session B (UNIN)
  → finally: close host (again, if needed) → cleanup (msiexec) → verdicts → report
```

---

## 5. Changes by file (Phase 1; in `CodeBase/` unless noted)

| File | Change |
|---|---|
| `skills/test-design/SKILL.md` | LOAD section: entry-point card, the 3 LOAD test shapes and keys, `seen_in_ui`, preconditions (L8, L11) |
| `skills/execute/host-interaction.md` | **New**, generic (§4.3) |
| `skills/hosts/autocad-plant3d.md`, `none.md` | Standard sections (§4.2); Plant 3D filled in and verified (build step 6) |
| `src/mpagent/models.py` | `Category` + LOAD · `Check` + `seen_in_ui` · `Status` + NEEDS_REVIEW · entry-point card in `Summary` |
| `src/mpagent/design/selfcheck.py` | LOAD rules (§4.1) |
| `src/mpagent/design/templates/understanding.md.j2` | Entry-point card |
| `src/mpagent/execute/windows_mcp.py` | Recorder keeps Snapshot UI text per test |
| `src/mpagent/execute/agent2.py` | Two sessions (L7); host executable in the input; load `host-interaction.md` for session A |
| `src/mpagent/execute/host.py` | **New:** find the host executable, close the host |
| `src/mpagent/execute/guardrails.py` | App tool only for the host executable; Process kill for host processes |
| `src/mpagent/execute/verdict.py` | `seen_in_ui`, NEEDS_REVIEW precedence (BLOCKED → ERROR → FAIL → NEEDS_REVIEW → PASS) |
| `src/mpagent/execute/templates/report.html.j2` | NEEDS_REVIEW colour and count; screenshot shown with LOAD results |
| `src/mpagent/config.py`, `.env.example` | `AGENT2_TIMEOUT_MIN` default 40 |
| `src/mpagent/pipeline.py` | Session A → close host → session B |
| `tests/` | New `test_host.py`; extend `test_selfcheck`, `test_verdict`, `test_models`, `test_guardrails`, `test_skills`, `test_agent2`, `test_pipeline` |
| Repo root docs | ARCHITECTURE.md (D8 scope, D5 two sessions, new D40+), ADR.md, AGENT_TOOLING_REVIEW.md (App and Process rules) |

---

## 6. Build steps (Phase 1, on `Dev-FunctionalTest`)

| # | Step | Done when |
|---|---|---|
| 1 | Models: LOAD, `seen_in_ui`, NEEDS_REVIEW, entry-point card | Strict-schema test passes; YAML round trip |
| 2 | Verdict: `seen_in_ui` + NEEDS_REVIEW | Unit tests: found, not found with screenshot, no snapshot |
| 3 | Self-check LOAD rules + `understanding.md` card | Unit tests per rule |
| 4 | Recorder: Snapshot UI text per test | Unit test with a fake Snapshot result |
| 5 | Skills: test-design LOAD section, `host-interaction.md`, host-notes sections | Team review; `test_skills` checks the headings |
| 6 | Plant 3D host notes verified on the machine (start, ready signal, popups, new P&ID drawing, ribbon tab in the UI tree, close without saving) | Every *(verify)* item resolved |
| 7 | `host.py`, guardrail changes, two Agent 2 sessions, pipeline wiring, 40 min limit | Unit tests; pipeline test with stand-ins |
| 8 | Report: NEEDS_REVIEW, screenshots with LOAD | Report test |
| 9 | Live run (elevated F5) | §7 acceptance |
| 10 | Docs | Updated after the grill |

---

## 7. Verification (Phase 1)

1. **Unit:** `uv run pytest` covers the new rules, `seen_in_ui`, NEEDS_REVIEW, the recorder, the host close and the guardrails; no API calls.
2. **Design only:** Agent 1 on the P&ID Exporter produces an entry-point card (ribbon tab "P&ID Exporter", items Export and Info; document kind "P&ID drawing", each cited) and three LOAD tests that pass the self-check.
3. **Live (elevated F5):**
   - LOAD-001 PASS (host started, no error dialog);
   - LOAD-002 PASS (new document of the needed kind open);
   - LOAD-003 PASS if "P&ID Exporter" is in the UI tree, otherwise NEEDS_REVIEW with the screenshot;
   - the host is closed by Agent 2 or by code; UNIN PASS; nothing left installed.
4. **Failure paths:** host won't start → LOAD-001 FAIL/ERROR, LOAD-002/003 BLOCKED, UNIN still PASS; unknown dialog → screenshot + ERROR, the host is closed by code; Agent 2 times out in session A → code closes the host, session B still uninstalls.

---

## 8. Risks (Phase 1)

| Risk | Mitigation |
|---|---|
| Creating a new document of the needed kind may need a project or dialogs (e.g. P&ID in Plant 3D) | Verify in build step 6 and write the exact steps in host notes; if a project is unavoidable, use the host's default/empty project, still no sample data |
| The ribbon tab isn't in the UI tree | `seen_in_ui` falls back to NEEDS_REVIEW with the screenshot (L4) |
| Slow host start (30–90 s), start page, trust dialogs | Ready signal and known popups in host notes; 3 min host wait; 40 min total |
| A weak model wanders in the host UI | Short fixed skill, App tool limited to the host executable, code closes the host, repeat limit (D36) |
| Licence/entitlement dialogs (this plug-in has `EntitlementApiWrapper.dll`) | Treated as an unknown dialog: screenshot, LOAD ERROR, host closed by code |
| The host is left running if the run is killed | Code closes it between sessions and in `finally`; killing F5 is covered by D39 |

---

## 9. Phase 2 (later): running features (FUNC)

Kept from plan v1, to be grilled separately once Phase 1 works:
- **Feature cards** for each documented feature (entry point, context, data kind, result, automatable yes/no); only safe features become tests, max 3, "Info/About" first.
- **Test-data catalogue** (`test_data/catalogue.yaml`) of approved sample files, e.g. host-shipped sample projects; **code copies** them into `run/sandbox/` before Agent 2.
- **File checks by code** (`file_exists`, `file_not_empty`, `json_valid`, `xml_valid`, `file_contains`) on outputs saved under `evidence\output\`.
- Optional **host command channels** (startup script, COM) from host notes, instead of clicking.
- Example for the P&ID Exporter: Info opens a dialog; Export on a sample P&ID drawing writes valid, non-empty JSON; content correctness = NEEDS_REVIEW.
