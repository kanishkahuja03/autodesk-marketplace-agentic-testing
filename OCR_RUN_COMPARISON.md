# OCR run comparison: Plant 3D (P&ID Connector Exporter)

> **Baseline:** `runs/pid-connector-exporter/20261026-200020`, on the current code (UI Automation name tools, no OCR), 2026-10-26. Result: **12 PASS**, `COMPLETED`.
> **OCR run:** _to be filled in after the build ([`OCR_UI_PLAN.md`](OCR_UI_PLAN.md))._
> **Source:** `run.log` and `trace.jsonl`. Trace times have **1 s resolution**. Windows-MCP tool times are **estimated** as the gap since the previous trace event. Model-call and name-tool times are exact.

## 1. Whole run by stage
| Stage | Baseline (s) | OCR run (s) | Δ |
|---|---|---|---|
| S0 intake | 1 | | |
| S1 static read | 1 | | |
| Agent 1 (design + self-check, 1 attempt) | 26 | | |
| Human review (y/n) | 5 | | |
| Preflight | 8 | | |
| **Agent 2 (execution)** | **498** | | |
| Kill host, leftovers, cleanup | 2 | | |
| Verdicts + judge + report | 45 | | |
| **Total** | **586 (9 min 46 s)** | | |

## 2. Agent 2: where the 495 s went
| Part | Baseline | OCR run | Δ |
|---|---|---|---|
| Model thinking (80 calls) | 294.1 s (59%) | | |
| Tools (Windows-MCP + name tools) | 192.5 s (39%) | | |
| Other (SDK, recording) | ~8 s (2%) | | |
| Model call median / max | 3.4 s / 6.8 s | | |
| Model calls with images / without (median) | 3.7 s / 2.8 s | | |
| Images sent to the model (total) | 172 in 60 calls | | |
| Tokens in / out / reasoning | 3,597,378 / 6,139 / 1,894 | | |

## 3. Per test (Agent 2)
| Test | Wall (s) | Model calls | Model (s) | Tools (s) | Tools used (calls) | OCR run wall (s) | Δ |
|---|---|---|---|---|---|---|---|
| ENV-001 | 17 | 5 | 13.9 | 1.0 | Registry 3, Snapshot 1 | | |
| INST-001 | 14 | 3 | 9.3 | 4.0 | PowerShell 2 | | |
| INST-002 | 10 | 3 | 8.5 | 2.0 | Registry 2 | | |
| INST-003 | 10 | 4 | 10.0 | 0.0 | FileSystem 3 | | |
| **LOAD-000** (start host, open project and drawing) | **209** | 26 | 88.5 | 119.0 | wait_for_host 6 (68 s), Snapshot 2 (27 s), click_ui 6 (19.5 s), Screenshot 7, type_ui 1, FileSystem 2, App 1 | | |
| LOAD-001 (ribbon tab visible) | 13 | 3 | 13.3 | 0.0 | Screenshot 2 (regions) | | |
| **LOAD-002** (ribbon button reachable) | **122** | 16 | 65.7 | 53.9 | Snapshot 3 (46 s), Screenshot 6, Click 5 (coordinates), find_ui 1 (4.9 s) | | |
| FUNC-001 (export to JSON) | 41 | 8 | 34.8 | 6.6 | Click 1 (coordinates), Screenshot 2, type_ui 1, wait_for_host 1, FileSystem 2 | | |
| UNIN-001 | 37 | 7 | 29.1 | 6.0 | PowerShell 2, Registry 3, Process 1 | | |
| UNIN-002 | 15 | 4 | 15.8 | 0.0 | FileSystem 3 | | |
| (final answer) | 6 | 1 | 5.2 | 0 | | | |
| ENV-000, UNIN-000 | code | | | | Run by code, not Agent 2 | | |

## 4. Per tool (Agent 2)
| Tool | Calls | Total (s) | Median (s) | Max (s) | OCR run calls / total | Δ |
|---|---|---|---|---|---|---|
| MCP Snapshot | 6 | 74.0 | 15.0 | 21.0 | | |
| wait_for_host | 7 | 70.9 | 5.0 | 30.2 | | |
| click_ui | 6 | 19.5 | 2.9 | 5.9 | | |
| MCP PowerShell | 4 | 8.0 | 2.0 | 4.0 | | |
| type_ui | 2 | 5.2 | 2.6 | 2.7 | | |
| find_ui | 1 | 4.9 | 4.9 | 4.9 | | |
| MCP Registry | 8 | 4.0 | 0.5 | 1.0 | | |
| MCP Screenshot | 17 | 4.0 | 0.0 | 1.0 | | |
| MCP FileSystem | 10 | 1.0 | 0.0 | 1.0 | | |
| MCP Click (by coordinates) | 6 | 1.0 | 0.0 | 1.0 | | |
| MCP App | 1 | 0.0 | 0.0 | 0.0 | | |
| MCP Process | 1 | 0.0 | 0.0 | 0.0 | | |

## 5. Every name-tool call (UI Automation today)
| Test | Call | Time (s) | Result | OCR run: engine / time (s) |
|---|---|---|---|---|
| LOAD-000 | wait_for_host | 10.72 | Host ready | |
| LOAD-000 | wait_for_host | 15.99 | Dialog opened ('Hinweis') | |
| LOAD-000 | click_ui "OK" (Button) | 0.33 | Clicked (button reported by wait_for_host) | |
| LOAD-000 | wait_for_host | 3.50 | Host ready | |
| LOAD-000 | click_ui "Open" (Button) | 1.75 | Clicked | |
| LOAD-000 | click_ui "Open..." (ListItem) | 2.80 | Clicked | |
| LOAD-000 | wait_for_host | **30.24** | **Timed out: the file dialog wasn't reported** | |
| LOAD-000 | type_ui "File name:" | 2.56 | Typed | |
| LOAD-000 | wait_for_host | 2.53 | Host ready | |
| LOAD-000 | click_ui "P&ID Drawings" (TreeItem, double) | 2.95 | Double-clicked | |
| LOAD-000 | click_ui "Area_1" (TreeItem, double) | 5.72 | Double-clicked | |
| LOAD-000 | click_ui "1-A1-1001" (TreeItem, double) | 5.92 | Double-clicked | |
| LOAD-000 | wait_for_host | 5.00 | Host ready | |
| LOAD-002 | find_ui "Export" | 4.94 | 2 matches | |
| FUNC-001 | type_ui "File name:" | 2.67 | Typed | |
| FUNC-001 | wait_for_host | 2.91 | Host ready | |

`click_ui` (UI Automation): **6 calls, median 2.9 s, total 19.5 s**. This is the time OCR clicks must beat on dialogs and the Project Manager tree.

## 6. The ribbon steps (what OCR is meant to speed up)
Today the ribbon goes through Screenshot → model estimates coordinates → Windows-MCP `Click`.

| Test | What happened | Time |
|---|---|---|
| LOAD-001 | 2 region Screenshots of the tab row; tab "P&ID Connector" seen; no click | 13 s |
| LOAD-002 | **5 coordinate Clicks**: 4 on the tab row (y ≈ 46: x 1055, 1097, 1194, 1180) and 1 at (37, 65). Also 6 Screenshots, **3 Snapshots of ribbon regions (46 s)** and 1 `find_ui("Export")` (4.9 s, 2 matches) | 122 s |
| FUNC-001 | 1 coordinate Click at (57, 96) on "P&ID exportieren", then a Screenshot and the save dialog | part of 41 s |

The ribbon tests (LOAD-001 + LOAD-002) took **135 s, 27% of Agent 2**. Of that, **46 s were Snapshots** of ribbon regions, which the Plant 3D navigation steps say not to take ("Screenshot only").

| Ribbon metric | Baseline | OCR run | Δ |
|---|---|---|---|
| Coordinate Clicks on the ribbon | 6 | | |
| Snapshots of ribbon regions | 3 (46 s) | | |
| Screenshots in LOAD-001/002 | 8 | | |
| Model calls in LOAD-001/002 | 19 (79.0 s) | | |
| LOAD-001 + LOAD-002 wall | 135 s | | |

## 7. Judge (verdict stage)
| Test | Calls | Time per call (s) | Verdict |
|---|---|---|---|
| LOAD-000 | 1 | 9 | PASS |
| LOAD-001 | 1 | 8 | PASS |
| LOAD-002 | 1 | 12 | PASS |
| FUNC-001 | 3 | 13, 15, 16 | PASS |

## 8. Verdicts
| Test | Baseline | OCR run |
|---|---|---|
| ENV-000, ENV-001, INST-001…003, LOAD-000…002, FUNC-001, UNIN-000…002 | 12 × PASS | |

## 9. Notes for reading the OCR run
- **The plug-in's UI is German** in this run: tab "P&ID Connector", panel "Werkzeuge", buttons "P&ID exportieren" and "Auswahl exportieren". The documents say "P&ID Exporter" and "Export". By the OCR rules (O6, O7), `click_ui("Export")` finds **no exact match and two "contains" matches**, so it goes to UI Automation. An exact name such as `click_ui("P&ID exportieren")` or `click_ui("P&ID Connector")` is what OCR can click directly.
- **Model time is 59% of Agent 2.** OCR can only cut tool time and the steps it saves (fewer Snapshots, fewer coordinate retries). Each saved step also saves a model turn of about 3–4 s.
- **Not OCR-related:** LOAD-000 lost about 30 s because `wait_for_host` didn't report the "Select File" dialog, then a Snapshot was taken to find it. Expect the same in the OCR run, since `wait_for_host` is unchanged.
- The breakdown is made with a read-only script (`run_breakdown.py`, kept outside the repo). The same script is run on the OCR run.
