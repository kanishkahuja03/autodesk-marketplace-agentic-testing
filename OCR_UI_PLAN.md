# Plan: OCR-first clicks for Agent 2 (Windows built-in OCR)

> **Status:** built 2026-10-26, after the grill-me review (decisions O1–O16 in §2): `execute/ocr.py`, OCR first in `ui_find.py`, `WindowsOcr` passed by `agent2.py`, skills and tests updated (`uv run pytest`: 287 passed). Live check (read-only `find_ui` on File Explorer): OCR found the labels; reading one window takes 0.03–0.3 s on the 1366×768 screen and 0.9 s for a window across both monitors, and listing the host's windows takes 0.6 s. Not yet run on Plant 3D. Builds on [`UI_FIND_TOOLS_PLAN.md`](UI_FIND_TOOLS_PLAN.md) (ADR-047, ADR-049, ADR-050).
> **Rule kept:** nothing in the code or the generic skills names a product. Host-specific rules stay in the host's navigation files.

## 1. Why
The find-by-name tools ask Windows UI Automation (UIA) for elements by name. Measured times in the latest runs (`trace.jsonl`):

| Run | Host | `click_ui` median | Notes |
|---|---|---|---|
| 20261021-142452 (Exporter) | Plant 3D | 1.8 s | Dialogs and Project Manager; a ribbon miss took 6.05 s |
| 20261022-165638 (Importer) | Revit | 15.3 s | Misses ("not found") took 42–54 s |
| 20261022-111530 (Tiny Tools) | Revit | 22.6 s | |

The Plant 3D **ribbon** isn't in the UIA tree. Today Agent 2 takes a Screenshot, the LLM estimates coordinates, and Windows-MCP `Click` clicks there.

**Goal:** build OCR as the first way to find click targets, then compare a Plant 3D run with a baseline run. Whether OCR stays is decided after the comparison.

## 2. Decisions
| # | Decision |
|---|---|
| O1 | **Engine:** Windows built-in OCR (`Windows.Media.Ocr`), local. No separate program to install. |
| O2 | **Scope:** `click_ui` and `find_ui`. **Typing stays UIA** (`type_ui`), because OCR sees a field's label, not the field. `wait_for_host` is unchanged. |
| O3 | **Order in `click_ui`:** 1) OCR → 2) UIA name search (today) → 3) "not found, use Windows-MCP" (today). |
| O4 | **`control_type` is ignored by OCR.** It is only used to break ties, through UIA. |
| O5 | **Matching:** case- and whitespace-insensitive (`normalize()`). It also matches a label split over two lines, and across the words of one line. **No look-alike characters** (1/I/l, 0/O are never treated as equal). |
| O6 | **Priority:** exact match first, then "contains". |
| O7 | **When OCR clicks:** exactly **one** exact match → click. No exact match and exactly **one** "contains" match → click. Several matches at either level → go to UIA. If UIA finds nothing, return the OCR matches with their coordinates, so Agent 2 can pick one with Windows-MCP `Click`. |
| O8 | **`find_ui`:** OCR first, listing its matches marked "(OCR, type unknown)" with coordinates. If OCR finds none, use UIA (today). |
| O9 | **Area read:** the **whole host window**, dialogs first, then the main window (drawing area and command line included). Wrong clicks are caught by Agent 2's Screenshot after each click and by the trace. |
| O10 | **Same chain for every call:** no ribbon special case. |
| O11 | **UIA skips its 2 s retry** (`RETRY_AFTER_S`) when OCR has already looked in the same call. |
| O12 | **No covered-window check.** The user keeps the screen unchanged during a run (accepted risk). |
| O13 | **No enlarging** of the capture before OCR, and no scale setting. |
| O14 | **No `.env` switch.** OCR is on for **every host**. Revit runs also use OCR from then on (untested). |
| O15 | **Baseline:** the user runs Plant 3D on the current code **before** the build. |
| O16 | **Comparison:** only a Plant 3D run is compared for now. Whether OCR stays is decided after the comparison. |

## 3. Design

### 3.1 New module `execute/ocr.py`
- **Capture:** only the host's windows. Window rectangles come from the existing UIA top-level lookup, which reads top-level windows only. Capture uses **pywin32** (`BitBlt`, already a dependency) in physical pixels (the existing `physical_pixels()`).
- **OCR:** `OcrEngine.TryCreateFromUserProfileLanguages()` on the captured bitmap. It returns lines and words with pixel boxes, which are converted to screen coordinates. It runs in the existing UIA worker thread.
- **Matching:** O5–O7, reusing `normalize()` / `order_matches()`. The click is at the centre of the matched words' combined box.
- **If the OCR engine can't start** (for example, no OCR language installed): log a warning once and continue with UIA only. The run is not stopped.

### 3.2 Changes to `ui_find.py`
- `UiFinder.click()` and `find()` try `ocr.py` first (O3, O8). `type_ui` and `wait_for_host` are unchanged.
- A UIA search after an OCR look skips the retry (O11).
- The result text says how the element was found, e.g. "Clicked 'Export' (found by OCR) at (x, y)".
- **Trace:** each `ui_find_call` gets `engine: "ocr" | "uia" | "reported"` (a button `wait_for_host` just reported), `ocr_seconds`, `uia_seconds`, `ocr_words` and, if OCR failed, `ocr_error`. The matched place is the centre in `matches`. This is the data for the comparison.

### 3.3 Dependencies
- `uv add` the WinRT packages for `Windows.Media.Ocr` and its imaging and stream types (exact package names confirmed when built).
- No new `.env` variable (O14).

### 3.4 Skills (runtime, `CodeBase/skills/`)
- `execute/ui-find.md`:
  - `click_ui` / `find_ui` also find text drawn on screen (OCR), so try them for any visible label, including areas not in the UI tree.
  - An OCR result has no element type.
- `hosts/navigation/plant3d-navigation-steps.md` §D (ribbon): a Screenshot to read the names as shown, then `click_ui("<tab or button text>")` without `control_type`. Use Screenshot + coordinates only if it answers "not found" or lists several matches. Icon-only buttons stay Screenshot + coordinates. Never a Snapshot of the ribbon.
- `hosts/navigation/plant3d-navigation.md` §4: the same rule in one line, so the two files agree.
- Revit navigation files: unchanged.

### 3.5 Tests (`uv run pytest`)
- New `tests/test_ocr.py`, using a fake OCR result:
  - word and line matching, two-line labels, no look-alike characters;
  - exact before contains, one vs several matches;
  - conversion to screen coordinates;
  - an engine that can't start.
- `test_ui_find.py`: the order OCR → UIA → fallback, the skipped retry, the `find_ui` OCR listing, and the trace fields.
- `test_skills.py`: phrase checks updated for the changed "Screenshot only" text (lines 167, 177, 181).

## 4. Not in scope
OCR typing; OCR in verdicts or in the judge; Revit testing; saving OCR captures as evidence (the Windows-MCP Screenshots stay the evidence); a covered-window check; image enlarging.

## 5. Risks
| Risk | Handling |
|---|---|
| Small, low-contrast or icon-only ribbon items are misread or missed | Fallback to UIA, then Screenshot + coordinates |
| Text in the drawing area or command line matches a name | Accepted (O9); the Screenshot after each click and the trace show it |
| Same text twice on screen (e.g. "Open") | Several matches → UIA decides by control type |
| A window covers the host and OCR reads or clicks it | Accepted (O12); the user keeps the screen unchanged |
| OCR can't tell disabled controls | The Screenshot after the click shows nothing happened; then the existing fallback |
| UI in another language | OCR uses the user-profile languages |
| Revit uses OCR without having been tested | Accepted (O14); checked later |

## 6. Comparison (Plant 3D, P&ID Connector Exporter)
- **Baseline:** the user's run on the current code, before the build (O15).
- **New run:** same inputs, `.env` and machine, after the build.
- **Compared from `trace.jsonl` and `run.log`:**
  1. Agent 2 total time
  2. `click_ui` / `find_ui` time per call, by engine
  3. Ribbon clicks: the baseline's Screenshot → model turn → `Click`, against the OCR `click_ui`
  4. Number of Screenshots, model calls and total model seconds
  5. Verdicts per test
- The decision whether OCR stays is made after the comparison (O16).

## 7. Build steps
1. `ocr.py` (capture, OCR, matching) + unit tests.
2. Wire it into `click_ui` / `find_ui` + the skipped retry + trace fields + tests.
3. Skill text updates + `test_skills.py`.
4. `uv run pytest`, all green.
5. A short manual check: OCR finds a ribbon tab in a running Plant 3D.
6. The user runs the comparison (§6).
