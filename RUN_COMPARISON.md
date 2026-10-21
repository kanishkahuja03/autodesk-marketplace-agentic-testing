# Run comparison: FUNC tests and performance (P&ID Connector Exporter on AutoCAD Plant 3D 2027)

> **What this page is:** a comparison of the three successful end-to-end runs that took the validation pipeline from "loads the plug-in" to "runs the plug-in's documented feature and checks its output", and then made it faster. All numbers come from each run's `run.log`, `trace.jsonl` and `results.json` under `CodeBase/runs/pid-connector-exporter/<run>/`.
> **Background:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (the pipeline), [`FUNC_TESTS_PLAN.md`](FUNC_TESTS_PLAN.md) (FUNC tests), [`UI_FIND_TOOLS_PLAN.md`](UI_FIND_TOOLS_PLAN.md) (find-by-name UI tools), [`ADR.md`](ADR.md) (decisions, incl. ADR-047).

---

## 1. Summary

| | Run 1: FUNC pass | Run 2: performance | Run 3: low LLM effort |
|---|---|---|---|
| Run folder | `20261016-172639` | `20261019-161125` | `20261021-115435` |
| What was new | First run where the plug-in's **Export feature ran and its JSON was checked** | **Find-by-name UI tools** (fewer UI-tree Snapshots); judge reads output files in full | Agent 2 **reasoning effort `low`**; name tools for dialogs; ribbon marked "Screenshot only" |
| Result | 13 PASS, **1 NEEDS_REVIEW** | **14 PASS** | 14 PASS, **1 FAIL** (see §4.3) |
| Export file produced | yes, 373 KB JSON | yes, 373 KB JSON | yes, 373 KB JSON |
| **Agent 2 (test execution)** | **15 min 57 s** | **9 min 33 s** (−40 %) | **8 min 43 s** (−45 %) |
| **Whole run** | 19 min 19 s | 12 min 5 s | 11 min 55 s |
| UI-tree Snapshots (count / time) | 12 / 548 s | 6 / 143 s | 6 / 198 s |
| Agent 2 steps (tool calls + records) | 81 | 77 | 66 |

**In one sentence:** the pipeline now installs the plug-in, checks that it loads in Plant 3D, runs its documented Export on a copy of a P&ID sample project, verifies the JSON it writes, and uninstalls it cleanly, in about 9 minutes of agent time instead of 16.

---

## 2. What the pipeline does (short)

```
S0 intake → S1 installer read → Agent 1 (designs cited tests) → human review → preflight
→ Agent 2 (runs the tests through Windows-MCP) → kill host → leftovers check → cleanup → verdicts + LLM judge → report
```

- **Agent 1** reads the app's documents and installer facts and writes `testcases.yaml` (ENV, INST, LOAD, **FUNC**, UNIN tests), each test citing the document it comes from.
- **Agent 2** executes them on the machine: install, start AutoCAD Plant 3D, open the sample project, find the plug-in's UI, run its Export, uninstall.
- **Code** decides PASS/FAIL from what Agent 2 observed; an **independent LLM judge** decides UI and content claims from screenshots and the produced files.
- **Generic by design:** nothing in the code or the generic skills names this plug-in or host; host knowledge lives in the host profile and its navigation files (data).

Test categories in these runs: ENV (host present), INST (install, registration, files, signature), LOAD (host starts, plug-in's tab and buttons present), **FUNC** (Export works), UNIN (uninstall, nothing left behind).

---

## 3. What changed between the runs

### Run 1 (`20261016-172639`): FUNC tests working
Built since the previous runs (all generic):
- **FUNC test category:** Agent 1 writes a *feature card* per documented feature and one FUNC test per testable feature, with one judged claim per documented result statement, plus a code check that a file was produced (`output_created`).
- **Sample context:** a sample project (`SAMPLES_DIR` in `.env`, here Plant 3D's `SampleProject`) is **copied into the run folder**; Agent 2 opens the copy, never the original.
- **LOAD-000 on the sample:** the host session opens the copied project and a P&ID drawing in it, and LOAD and FUNC run there.
- **Output folder per test:** whatever the feature saves goes to `evidence/<test_id>/`; code checks it.
- **Host navigation file** (`skills/hosts/navigation/plant3d-navigation.md`): where Plant 3D's start page, Project Manager, file dialogs and ribbon are (host-only, never names the plug-in).
- **Generic fixes:** `WaitFor` takes plain text (a regex never matched and wasted 105 s per run); dialogs are found with a Snapshot instead of `WaitFor` (that had cost ~5 min per run).

Settings: `OPENAI_MODEL=gpt-5.5`, default reasoning effort, judge saw the first **15,000 characters** of output files.

### Run 2 (`20261019-161125`): performance (fewer Snapshots)
- **Find-by-name UI tools** (ADR-047, `CodeBase/src/mpagent/execute/ui_find.py`): `find_ui`, `click_ui`, `type_ui` find an element of the host's windows **by its name** through Windows UI Automation (exact name first, then "contains"; first match used) and click or type into it. **Windows-MCP stays the fallback.** Same protection as Windows-MCP calls: host windows only, the same call at most 3 times, every call traced.
- **Step sequences for the host** (`skills/hosts/navigation/plant3d-navigation-steps.md`): e.g. *file dialog → `type_ui("File name:", <Project.xml>)` → `click_ui("P&ID Drawings", double)` → folder → drawing*.
- **Judge reads output files in full** (`JUDGE_FILE_EXCERPT_CHARS` unset = no limit). This turned Run 1's NEEDS_REVIEW into PASS.
- Switch `AGENT2_UI_FIND_TOOLS=true` (`false` = exactly the behaviour of Run 1).

### Run 3 (`20261021-115435`): low LLM effort and fewer Snapshots by rule
- **`AGENT2_REASONING_EFFORT=low`** (new `.env` setting; empty = model default as before). Agent 1 and the judge unchanged.
- **Skill rules:** answer dialogs with `click_ui("<button>")` instead of a Snapshot; take a Screenshot before a Snapshot; the ribbon is **"Screenshot only"** (it is not in the UI tree, so no name tools and no Snapshots there).

---

## 4. Results per test

| Test | What it checks | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|
| ENV-000 | plug-in not installed before (code) | PASS | PASS | PASS |
| ENV-001 | supported Plant 3D version installed | PASS | PASS | PASS |
| ENV-002 | 64-bit OS | — | — | PASS |
| INST-001 | silent install, exit code 0 | PASS | PASS | PASS |
| INST-002 | Uninstall entry, version 1.0.5 | PASS | PASS | PASS |
| INST-003 | bundle files installed | PASS | PASS | PASS |
| INST-004 | installer signature valid, signer matches | PASS | PASS | PASS |
| LOAD-000 | Plant 3D starts, copied SampleProject + P&ID drawing open | PASS | PASS | PASS |
| LOAD-001 | plug-in's tab present | PASS + finding | PASS + finding | PASS + finding |
| LOAD-002 | its Export button reachable | PASS + finding | PASS + finding | **FAIL** |
| **FUNC-001** | Export writes the drawing to JSON (3 documented claims + file produced) | **NEEDS_REVIEW** | **PASS** | **PASS** |
| UNIN-000 | nothing left behind (code) | PASS | PASS | PASS |
| UNIN-001…003 | silent uninstall, entry removed, files removed | PASS | PASS | PASS |

(ENV-002 is written by Agent 1 when it chooses to; the plans differ slightly between runs.)

### 4.1 Findings (all runs)
- **Documentation mismatch:** the documents say the tab is "P&ID Exporter" and the button "Export"; the app shows the tab **"P&ID Connector"** and the button **"P&ID exportieren"** (in a "Werkzeug" drop-down).
- **Localisation:** the plug-in's UI is in German on this machine (its own language setting).

### 4.2 Run 1's NEEDS_REVIEW → PASS in Run 2
The third FUNC claim says the export contains "assets and lines … image and position data". The JSON is ~373,000 characters; the judge saw only the first 15,000, where only lines appear (assets start at character 73,901), so it answered "needs review" instead of guessing. With the full file (Run 2, Run 3) the judge confirmed `LineElements` (26), `AssetElements` (90), `AnnotationElements` (6), image (`Img`) and position data: **PASS**.

### 4.3 Run 3's FAIL on LOAD-002
LOAD-002's claim is the documents' own wording: *the "P&ID Exporter" tab contains the "Export" button.* In Run 3 Agent 2 showed the plug-in's tab without opening its "Werkzeug" drop-down; the judge saw the tab **"P&ID Connector"** with one button **"Werkzeug"**, and neither name the documents give, and answered **FAIL**. This is treated as a **correct FAIL**: the documented names are not what the app shows. (In Runs 1 and 2 Agent 2 opened the drop-down, the judge saw "P&ID exportieren" and passed it *with a documentation-mismatch finding*. The difference is how far Agent 2 explored, which the lower reasoning effort reduced.)

---

## 5. Time: where it went

### 5.1 Per pipeline stage

| Stage | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| S0 intake + S1 installer read | 3 s | 2 s | 2 s |
| Agent 1 (test design, 1 LLM call) | 25 s | 22 s | 26 s |
| Human review of the tests | 1 min 50 s | 48 s | 1 min 18 s |
| Preflight (elevation, Windows-MCP, ENV-000, footprint) | 7 s | 8 s | 9 s |
| **Agent 2** | **15 min 57 s** | **9 min 33 s** | **8 min 43 s** |
| Kill host, leftovers check, cleanup | 4 s | 2 s | 2 s |
| Verdicts, LLM judge (6 calls), report | 53 s | 70 s | 75 s |
| **Total** | **19 min 19 s** | **12 min 5 s** | **11 min 55 s** |

The judge takes a little longer from Run 2 on because it reads the whole 373 KB JSON for the content claim.

### 5.2 Agent 2 per test

| Test | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| ENV + INST (code-like checks) | 1 min 5 s | 1 min 1 s | 1 min 4 s |
| **LOAD-000** (start Plant 3D, open project copy + drawing) | **8 min 53 s** | **4 min 8 s** | **5 min 5 s** |
| LOAD-001 (tab) | 11 s | 21 s | 13 s |
| LOAD-002 (button) | 1 min 31 s | 1 min 11 s | 14 s |
| **FUNC-001** (run Export, save JSON) | **2 min 44 s** | **57 s** | **56 s** |
| UNIN (3 tests) | 1 min 23 s | 1 min 44 s | 1 min 1 s |

### 5.3 Agent 2 per tool

| Tool | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| **Snapshot** (Windows-MCP, whole UI tree) | **12 calls, 548 s (46 s avg)** | **6 calls, 143 s (24 s avg)** | 6 calls, 198 s (33 s avg) |
| Screenshot | 8 calls, 31 s | 13 calls, 55 s | 8 calls, 30 s |
| Click (Windows-MCP, by coordinates/label) | 9 calls, 46 s | 6 calls, 30 s | 5 calls, 20 s |
| **Name tools** (`click_ui`, `type_ui`, `find_ui`) | — | 6 calls, 50 s | 6 calls, 33 s |
| WaitFor (host start-up) | 43 s | 41 s | 44 s |
| Wait | 70 s | 33 s | 39 s |
| PowerShell, Registry, FileSystem (install/uninstall checks) | 134 s | 133 s | 90 s |

Each figure is the time between two consecutive steps in `trace.jsonl` (the model deciding + the tool running).

### 5.4 What the improvements actually did

**Snapshots (Run 1 → Run 2).** A Windows-MCP Snapshot dumps Plant 3D's whole UI tree (~40,000 characters with a project open) and took ~46 s. Agent 2 needed one before almost every click, because Windows-MCP can click only by coordinates or by a label from a Snapshot. With the name tools, the project path was done like this in Run 2 (tool time per call):

| Step | Call | Tool time |
|---|---|---|
| Project file in the "Select File" dialog | `type_ui("File name:", "…\context\SampleProject\Project.xml", Enter)` | 3.9 s |
| Expand the P&ID group | `click_ui("P&ID Drawings", TreeItem, double)` | 3.2 s |
| Expand the area folder | `click_ui("Area_1", TreeItem, double)` | 2.9 s |
| Open the drawing | `click_ui("1-A1-1001", TreeItem, double)` | 3.0 s |
| Save path in the plug-in's export dialog | `type_ui("File name:", "…\evidence\FUNC-001\…json", Enter)` | 2.9 s |

Result: LOAD-000 **8 min 53 s → 4 min 8 s**, FUNC-001 **2 min 44 s → 57 s**.

**Reasoning effort `low` (Run 2 → Run 3).** Each step got about **1 s faster** (e.g. a Click 5.0 → 4.0 s, a Registry read 4.6 → 3.8 s) and Agent 2 needed fewer steps (77 → 66): **−50 s overall**. The trade-off: Agent 2 explored less (it didn't open the drop-down in LOAD-002) and kept a project that Plant 3D had remembered from an earlier run instead of opening this run's copy (same project name, same content; the user's original was not touched).

**Why Run 3's LOAD-000 was slower than Run 2's (5 min 5 s vs 4 min 8 s).** One Snapshot was taken while Plant 3D was still finishing its start-up right after the plug-in's start-up notice was confirmed: **78 s** for that single call (the host answers UI Automation slowly while busy). At the same moment two name searches ("Open", "OK") answered "not found" within about a second, because the window wasn't exposing its elements yet; Windows-MCP clicked them by coordinates instead (the fallback working as designed). With `low` effort Agent 2 also took a Snapshot before each of the three tree clicks (~30 s) although the name tools made them unnecessary.

---

## 6. What is fixed and what remains

| Topic | Status |
|---|---|
| FUNC test runs the documented feature and checks its file | **Done** (all three runs) |
| Content claims about large output files | **Done**: judge reads the whole file (Run 2 on) |
| Waiting 105 s for the host window / ~5 min for dialogs | **Fixed** before Run 1 |
| UI-tree Snapshots as the main cost | **Reduced** 548 s → 143–198 s |
| Host start-up (Plant 3D loading) | ~41–44 s, not reducible |
| Snapshots while the host is still busy (Run 3: 78 s) | open: wait until the host is idle (a Screenshot shows it) before any Snapshot |
| Remaining avoidable Snapshots (before tree clicks, ~30 s) | open: the steps file says not to; `low` effort ignored it |
| Model thinking per step (~3–5 s × ~70 steps) | partly addressed by `low` (−1 s/step), at the cost of less thorough exploration |
| Host remembering the last project | open: always open the run's own `Project.xml` by path, even when a project with the same name is shown |

**Recommended setting for now:** `AGENT2_REASONING_EFFORT` empty (model default) or `medium`, because `low` saved only ~50 s and made Agent 2 less thorough. Realistic next target: Agent 2 at ~7 min with the remaining Snapshot cuts.

---

## 7. Where to look

| Item | Path (under `CodeBase/runs/pid-connector-exporter/<run>/`) |
|---|---|
| Human report with screenshots and judgements | `report.html` |
| Verdicts | `results.json` |
| Test plan Agent 1 wrote | `testcases.yaml`, `understanding.md` (feature cards, open questions) |
| Every tool call with time | `trace.jsonl` (`mcp_call`, `ui_find_call`, `judge_request` …) |
| The exported JSON | `evidence/FUNC-001/*.json` |
| The copied sample project | `context/SampleProject/` |

| Code | Path (under `CodeBase/`) |
|---|---|
| Find-by-name tools | `src/mpagent/execute/ui_find.py`, `skills/execute/ui-find.md` |
| Sample copy, output folders, Agent 2 input | `src/mpagent/execute/context.py` |
| FUNC tests, feature cards, self-check | `src/mpagent/design/agent1.py`, `selfcheck.py`, `skills/test-design/SKILL.md` |
| Judge (screenshots, full output files) | `src/mpagent/execute/judge.py`, `skills/execute/judge.md` |
| Host navigation (Plant 3D only, data) | `skills/hosts/autocad-plant3d.md`, `skills/hosts/navigation/*.md` |
| Settings | `.env.example`: `SAMPLES_DIR`, `AGENT2_UI_FIND_TOOLS`, `AGENT2_REASONING_EFFORT`, `JUDGE_FILE_EXCERPT_CHARS`, `JUDGE_MAX_IMAGES` |
