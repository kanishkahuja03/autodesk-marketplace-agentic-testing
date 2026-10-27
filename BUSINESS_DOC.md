# Business Document: Marketplace App Validation Agents

> Status as of 2026-10-23, from the current code on branch `Dev-Revit-Support`.

## 1. Problem
Store QA for desktop plug-ins and apps is done by hand. A reviewer installs the app, checks that it loads in its host, tries its features and checks that it uninstalls cleanly. This is slow, and the results differ from one reviewer to the next.

## 2. Solution
An AI pipeline that takes an app's **documentation and installer** and produces a **test report with evidence**:

| Step | Who | What |
|---|---|---|
| Read inputs | Code | Extracts text from the documents and facts from the installer, without running it |
| Design tests | Agent 1 (LLM) | Writes test cases. Each test cites the documentation line it comes from |
| Human review | Reviewer | Approves the test plan (y/n) before anything touches the machine |
| Run tests | Agent 2 (LLM) | Installs the app, opens the host, uses the features and uninstalls, through Windows UI automation |
| Decide verdicts | Code + LLM judge | Code decides PASS/FAIL from the recorded values. A separate LLM judge decides UI claims from screenshots |
| Report | Code | `report.html` and `results.json` with evidence (logs, screenshots, produced files) |

**Generic by design:** the core code contains no product-specific logic. Each host application is described in data files (host notes), so a new host can be added without core code changes.

## 3. What is tested
| Category | Checks |
|---|---|
| ENV | App not installed before the run; machine values resolved |
| INST | Silent install succeeds; signature; Programs and Features entry; installed files |
| LOAD | Host starts, the app is loaded, its documented UI entry point (ribbon, menu, button) is visible |
| FUNC | A documented feature is run and produces a result (for example a file) |
| UNIN | Silent uninstall succeeds; entry and files removed; leftover check |

Verdicts: **PASS, FAIL, NEEDS_REVIEW, BLOCKED, ERROR**. The report also lists **findings**, for example "documentation says X, the app shows Y".

## 4. Value
- Repeatable results: verdicts are decided by code, not by the agent that ran the test.
- Every result is traceable to a documentation line and to evidence.
- The reviewer's job shifts from doing the tests to approving the plan and reading the report.

## 5. Current status
| Host | Demo app(s) | Status |
|---|---|---|
| AutoCAD Plant 3D 2027 | P&ID Connector Exporter | Built (ENV, INST, LOAD, FUNC, UNIN) |
| Revit 2027 | Tiny Tools, P&ID Connector Importer | In progress (initial support committed, further work ongoing) |

Latest recorded runs (verdict counts from `run.log`; the causes of the FAIL/BLOCKED/ERROR results are not analysed here):

| App | Run | Result |
|---|---|---|
| P&ID Connector Exporter | 20261021-142452 | 14 PASS |
| P&ID Connector Importer (Revit) | 20261022-165638 | 10 PASS, 2 FAIL, 7 BLOCKED |
| Tiny Tools (Revit) | 20261022-111530 | 10 PASS, 3 FAIL, 3 NEEDS_REVIEW, 1 ERROR |

## 6. Scope limits (POC)
- Inputs are copied by hand into `inputs/<app>/`. There is no Marketplace integration.
- MSI and ZIP bundle installers are read fully; EXE installers give basic facts only.
- One sample file or folder per run (`SAMPLES_DIR`), switched by hand.
- Runs on the developer's admin machine. There is no VM or sandbox isolation yet.

## 7. Prerequisites
- Windows machine, run as administrator, with the host application installed.
- OpenAI API key and model (in `CodeBase/.env`).
- Windows-MCP 0.8.6 installed (`uv tool install windows-mcp==0.8.6`).

## 8. Risks and how they are handled
| Risk | Handling |
|---|---|
| The agent changes the machine | Tool allow-list (13 tools); PowerShell command allow-list; read-only registry and file access; guardrails checked in code before every call |
| Prompt injection from documents or UI text | Agent 1 has no tools; Agent 2 treats all text as data |
| UI automation is fragile or slow | Find-by-name tools through Windows UI Automation; time and turn limits; restart at most once per test |
| Agent grades its own work | Verdicts by code; UI claims by a separate judge that only sees the evidence |
| App left installed after a failed run | Automatic cleanup (`msiexec /x`) at the end of every run |

## 9. Not built yet (from ARCHITECTURE.md §13)
VM / Windows Sandbox isolation, feedback from Agent 2 back to Agent 1, record-and-replay of tool calls, a full EXE installer reader, host command channels (for example COM), Robot or TestRail export, and testing both uninstall paths (silent and UI) in one run.
