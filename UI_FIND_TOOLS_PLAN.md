# Plan: find-by-name UI tools for Agent 2 (Option A, pywinauto, in-process)

> **Status:** built 2026-10-19 (decisions G1–G7 in §8); recorded as ADR-047 and in ARCHITECTURE.md D5. Not yet run live. Step sequences live in a separate host file (`navigation_steps:` in the host profile → `skills/hosts/navigation/plant3d-navigation-steps.md`) and the generic rules in `skills/execute/ui-find.md`, both loaded only with the switch on. Builds on [`FUNC_TESTS_PLAN.md`](FUNC_TESTS_PLAN.md) (Q14: navigation file; dialog rule) and [`ARCHITECTURE.md`](ARCHITECTURE.md). Once agreed, it becomes `FUNC_TESTS_PLAN.md` §8 Q15 / ARCHITECTURE.md D68+.
> **Rule kept:** nothing in the code or the generic skills names a product. The tools know no host and no app; names come from the host's navigation file (host) or the test's claims (app).

---

## 1. Why

Run 20261016-172639 (all tests pass, FUNC-001 exported a 373 KB JSON) took **15 min 53 s** in Agent 2. Measured from `trace.jsonl`:

| | Calls | Time |
|---|---|---|
| Windows-MCP `Snapshot` (whole UI tree, ~40,000 characters once a project is open) | 12 | **548 s (≈46 s each)** |
| All other steps (clicks, screenshots, waits, checks; mostly the model deciding) | ~73 | ~405 s |

The navigation file **was** followed, but Windows-MCP can click only by coordinates or by a label number from a Snapshot, so Agent 2 took a full Snapshot before almost every click. A tool that finds **one element by its name** avoids that.

## 2. Goal and non-goals

**Goal:** Agent 2 acts on host UI elements by name (`click_ui("P&ID Drawings", double=True)`) in about 1–2 s per action, following the navigation file's steps; Windows-MCP stays as the fallback and for screenshots.

**Non-goals:** no change to verdicts, judge, Agent 1, the test plan format, the guardrails or the report; no new server; no scripted replay without the LLM; ribbon items (not in the UI Automation tree) stay on the Screenshot + coordinates fallback.

## 3. Additive, existing code works as it is

- **One switch in `.env`:** `AGENT2_UI_FIND_TOOLS=true|false`, **on by default** (G5). With `false`, Agent 2 gets **exactly** today's instructions and tools: nothing new is registered, the new skill paragraph and navigation steps are not added.
- The tools are registered **only** when the plan uses the host (same condition as the host-interaction skill today, `host_launch(plan) is not None`).
- Windows-MCP, its 13 allowed tools, the guardrails, `record_observation`, the evidence recorder and every existing test stay unchanged. All existing unit tests must still pass unchanged (only new tests are added, plus phrase checks for the new skill text).

## 4. Design

### 4.1 New module `CodeBase/src/mpagent/execute/ui_find.py`
- **Library:** pywinauto, `uia` backend (`uv add pywinauto` from `CodeBase/`). Same Windows UI Automation that Windows-MCP uses, but a targeted search instead of a full tree dump.
- **Where it searches:** only the **host's windows**: top-level windows of the processes in `HostLaunch.processes` (from the host profile), including their owned dialogs (e.g. the file dialog). Never the console, never other programs. Process IDs come from the existing `execute/host.py` `running_pids()`.
- **Search (G3):** **exact name first** (case-insensitive), then **"contains"** only if nothing matches exactly; optional `control_type` (e.g. `Button`, `TreeItem`, `Edit`, `ListItem`) to narrow it. Bounded: a time limit (~5 s) per search, then "not found".
- **Pure matching** (`match(nodes, name, control_type)`) separated from UIA access, so it is unit-testable without a desktop.

### 4.2 Three tools for Agent 2 (Agents SDK `function_tool`, like `record_observation`)

| Tool | Does | Returns |
|---|---|---|
| `find_ui(name, control_type=None)` | searches, changes nothing | up to 10 matches: name, type, window, centre point, enabled |
| `click_ui(name, control_type=None, double=False)` | clicks the **first match** (exact before "contains", G4) | "clicked <name> (<type>) at …"; none → "not found, use Snapshot/Screenshot" |
| `type_ui(name, text, control_type="Edit", press_enter=False)` | focuses the first matching field and types | "typed into …" or not found as above |

- Every call is traced to `trace.jsonl` (`ui_find_call`: arguments, matches, result, duration), using the existing `runlog.Trace`.
- No screenshot is taken by these tools (G7); evidence for the judge stays Agent 2's `Screenshot` calls (rules unchanged).
- **Same protection as MCP calls (G1):** host windows only; the same call with the same arguments at most 3 times per run (like D36); every call traced.
- Errors (COM, timeouts) are caught and returned as text; a tool problem never crashes the run.

### 4.3 Wiring (`CodeBase/src/mpagent/execute/agent2.py`)
- In `_run()`: if the switch is on and `host is not None`, add the three tools to `tools=[...]` next to `record_observation`.
- `config.py`: one new setting `agent2_ui_find_tools: bool` (default `true`, G5).

### 4.4 Skill text
- **`skills/execute/host-interaction.md`** (generic, added only when the switch is on, e.g. as a separate file `execute/ui-find.md` appended by `instructions()`): "When you know an element's name (from the navigation file, a claim or a dialog), use `find_ui` / `click_ui` / `type_ui` first. Use Windows-MCP (Screenshot + click by coordinates) when the name is unknown, not found, or the element isn't in the UI tree (e.g. the ribbon), without trying the name tools there first (G6); Screenshots for evidence as today." The existing "never repeat the action while waiting" and action-class rules apply as they are.
- **`skills/hosts/navigation/plant3d-navigation.md`**: add the paths as numbered steps with the exact names (below). Prose stays for the fallback.

### 4.5 Navigation steps (names verified in run 20261016-172639, `evidence/0xx_Snapshot_ui.txt`)
*Open a project and a drawing in it (Project Manager):*
1. `click_ui("Open", control_type="Button")` beside the project combo box (Project Manager) → the project list expands. *(The quick-access toolbar also has an "Open"; if the first match opens the wrong thing, Agent 2 falls back to Screenshot + coordinates, G6.)*
2. `click_ui("Open...", control_type="ListItem")`.
3. `type_ui("File name:", "<full path of the copy's Project.xml>", press_enter=True)` (the "Select File" dialog).
4. `click_ui("P&ID Drawings", control_type="TreeItem", double=True)` → its folders appear (e.g. "Area_1").
5. `click_ui("<folder>", control_type="TreeItem", double=True)` → its drawings appear.
6. `click_ui("<drawing>", control_type="TreeItem", double=True)` → the drawing opens; then **one Screenshot** for evidence.

*Open a single drawing:* `OPEN` on the command line → `type_ui("File name:", "<full path>", press_enter=True)`.
*Save dialog of a feature:* `type_ui("File name:", "<full path in the output folder>", press_enter=True)`.
*Ribbon / plug-in tabs and buttons:* not in the UI tree → Screenshot + coordinates (fallback, unchanged).

## 5. Build steps

| # | Step | Done when |
|---|---|---|
| 1 | `uv add pywinauto`; `config.py` switch (default `true`) | `uv run pytest` passes unchanged |
| 2 | `ui_find.py`: matching + UIA access + host-window guard + repeat limit | unit tests: exact before "contains", type filter, first match, not found, non-host windows never searched, 4th identical call rejected, errors returned as text |
| 3 | Tools + wiring in `agent2.py` (only with the switch and a host) | tests: tools absent when off / no host; present when on; instructions unchanged when off |
| 4 | Skill text (`execute/ui-find.md`) + navigation steps | `test_skills`: generic files name no product; navigation names no app; new phrases present |
| 5 | Manual smoke check with Plant 3D open: `find_ui("P&ID Drawings")` | returns the tree item in ~1–2 s |
| 6 | Live run, switch `true` | §6 |
| 7 | Docs | `FUNC_TESTS_PLAN.md` §8 Q15, ARCHITECTURE.md / ADR entry |

## 6. Verification
1. `uv run pytest` from `CodeBase/`: all existing tests pass unchanged; the new tests pass.
2. Live run with `AGENT2_UI_FIND_TOOLS=false`: same behaviour as run 20261016-172639 (proves nothing changed).
3. Live run with `true` (P&ID Exporter, `SAMPLES_DIR` = SampleProject): the same verdicts (13 PASS + FUNC-001 file in `evidence/FUNC-001/`); from `trace.jsonl`: LOAD-000 uses `click_ui`/`type_ui` for the Project Manager path, ≤ 2 Snapshots in LOAD-000, Agent 2 total **under 8 min** (target; today 15.9).

## 7. Risks

| Risk | Mitigation |
|---|---|
| pywinauto/COM call hangs or throws inside our process | per-call time limit, all exceptions returned as text; switch to `false` restores today's behaviour |
| Same name in several places ("Open" in the toolbar and the Project Manager) | first match is clicked (G4); navigation steps give `control_type`; a wrong result is seen in the next Screenshot and Agent 2 falls back (G6) |
| An element is not in the UI tree (ribbon) | "not found" → the existing Screenshot fallback |
| Elevation: the run is elevated (msiexec), the host too | same process rights as Windows-MCP today; tools act only on host windows |
| A plug-in's localised UI (German labels) | names for app elements come from the claims and U1, as today; the tools only match what is on screen; fallback stays |

## 8. Grill decisions (2026-10-19)

| Q | Decision |
|---|---|
| G1 (ADR-005 / D5) | **Reversed openly, narrow scope:** a new ADR says that besides Windows-MCP, Agent 2 has three local UI tools (find, click, type by element name), acting on the host's windows only, behind the `.env` switch; D5's exception list is extended. The tools get the same protection as MCP calls: host windows only, the same call at most 3 times (like D36), every call traced. |
| G3 (matching) | **Exact name first** (case-insensitive), **then "contains"** only if nothing matches exactly. |
| G4 (several matches) | **Keep it simple for the POC: click the first match** (exact matches before "contains" matches). No `within` / `nth`. Where the navigation steps know a name occurs twice (e.g. "Open"), they give the element type (`control_type`) so the first match is the right one. |
| G5 (switch default) | **On by default** (`AGENT2_UI_FIND_TOOLS=true`); `false` gives exactly today's behaviour. Windows-MCP stays the fallback. |
| G6 (fallback) | Agent 2 uses Windows-MCP (Screenshot + click by coordinates) **whenever a name isn't found or the element isn't in the UI tree** (e.g. the ribbon), without first trying the name tools there. Note: LOAD-000 still needs **one Snapshot** before it is recorded (its `window_in_ui` check reads the Snapshot text, D46), so "≤ 2 Snapshots in LOAD-000" stays the target. |
| G7 (evidence) | The tools take **no screenshots**; Agent 2's own Screenshots after each step stay the judge's evidence. |
| G8 (after run 20261019-161125, 2026-10-19) | Agent 2 9 min 33 s (was 15 min 53 s). Next cuts: (1) start-up notices and the Project Manager's Open steps through `click_ui` without a Snapshot first; (2) areas marked "Screenshot only" (the ribbon) get neither name tools nor Snapshots, even for a claim's names; (3) `AGENT2_REASONING_EFFORT` in `.env` (empty = the model's default, as before). |
| G2 (speed) | **No separate measurement step;** build as planned and measure in the live run. Must hold: Windows-MCP stays the fallback whenever a name isn't found or is ambiguous, today's behaviour is unchanged with the switch off, and both kinds of calls (new tools and Windows-MCP) are logged in `trace.jsonl`. |

## 9. Open points to confirm
1. ~~Default of the switch~~: decided in G5 (on).
2. ~~When to fall back~~: decided in G6.
