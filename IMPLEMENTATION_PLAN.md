# Implementation Plan: Marketplace App Validation Agents (as built)

> Status as of 2026-10-23, from the current code on branch `Dev-Revit-Support`. Describes what is built today. Design decisions: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`ADR.md`](ADR.md).

## 1. Tech stack
| Area | Choice |
|---|---|
| Language / tooling | Python 3.12, uv, pytest |
| Agents | OpenAI Agents SDK (`openai-agents`); one model for all agents (`OPENAI_MODEL`) |
| Desktop automation | Windows-MCP 0.8.6 (13 allowed tools) + own find-by-name tools (UI Automation via comtypes, input via pywinauto) |
| Data contracts | Pydantic (`models.py`) |
| Inputs | pypdf, python-docx, BeautifulSoup, msi.dll (ctypes), `expand.exe`, zipfile |
| Outputs | Jinja2 (HTML / Markdown), ruamel.yaml |
| CLI / config | Typer (`uv run mpagent inputs/<app>`, or F5 in Visual Studio), python-dotenv |

## 2. Pipeline (one run, one run folder `runs/<app>/<timestamp>/`)

| # | Step | Module | Output |
|---|---|---|---|
| 1 | **S0 Intake**: classify files, extract document text, hash, read the claimed signer | `design/intake.py` | `documents/D*.txt`, `intake_manifest.json` |
| 2 | **S1 Static read**: MSI tables, bundle manifest, embedded docs, UI text from binaries (U1). Nothing is run | `design/static_read.py`, `msi.py`, `ui_text.py` | `installer_facts.json` |
| 3 | **Agent 1**: designs cited tests (no tools, structured output); code self-check with up to 2 retries; adds built-in ENV-000, LOAD-000, UNIN-000 | `design/agent1.py`, `selfcheck.py`, `evidence.py` | `testcases.yaml`, `understanding.md` |
| 4 | **Human review**: y/n in the console | `pipeline.py` | stops if "n" |
| 5 | **Preflight**: admin check, Windows-MCP tool list, ENV-000, host not running, footprint baseline | `execute/preflight.py`, `footprint.py` | baseline files |
| 6 | **Agent 2**: runs the tests through Windows-MCP and the find-by-name tools; records each test with `record_observation` | `execute/agent2.py`, `windows_mcp.py`, `ui_find.py`, `guardrails.py` | `observations.json`, `evidence/` |
| 7 | **Kill host + crash check** | `execute/host.py` | crash events file |
| 8 | **UNIN-000 leftovers**: footprint diff | `execute/footprint.py` | observation |
| 9 | **Cleanup**: `msiexec /x` if the app is still installed | `execute/cleanup.py` | `evidence/cleanup.log` |
| 10 | **Verdicts**: code checks; LLM judge for UI claims | `execute/verdict.py`, `judge.py` | per-test status |
| 11 | **Report** | `execute/report.py` | `results.json`, `report.html` |

Steps 7–11 always run once Agent 2 has started. A run ends with `COMPLETED` (exit 0), `STOPPED` (exit 1) or `CRASHED` (exit 2).

## 3. Agents
| Agent | Tools | Skills (Markdown instructions) | Output |
|---|---|---|---|
| Agent 1: test designer | None | `skills/test-design/SKILL.md` + all host notes | `TestPlan` |
| Agent 2: test executor | 13 Windows-MCP tools, `record_observation`, `find_ui` / `click_ui` / `type_ui` / `wait_for_host` | `skills/execute/windows-installer.md`, `evidence.md`, `host-interaction.md`, `ui-find.md` + host note and navigation files | `Agent2Result` |
| Judge | None (receives screenshots as images) | `skills/execute/judge.md` | `Judgement` |

Windows-MCP tools allowed: PowerShell, Registry, FileSystem, Process, App, Snapshot, Click, Type, Shortcut, WaitFor, Wait, Screenshot, Scroll.

## 4. Safety controls (in code)
- **Tool allow-list**, enforced twice: the Windows-MCP `--tools` flag and the SDK tool filter.
- **Guardrail before every call:**
  - PowerShell must start with an allowed command (msiexec, read-only queries); no chaining or redirection.
  - Install at most once; no uninstall while the host runs.
  - Only the host executable may be launched; only the host or msiexec may be killed.
  - Waits are capped; repeated identical calls are blocked.
- **Evidence rules:** observations must name files that exist in the run folder.
- **Limits:** turn and time limits (with extra per FUNC test); only the last N screenshots are re-sent to the model.

## 5. Host support (as data)
| Host | Files | Status |
|---|---|---|
| AutoCAD Plant 3D 2027 | `skills/hosts/autocad-plant3d.md`, `navigation/plant3d-navigation*.md` | Built |
| Revit 2027 | `skills/hosts/revit.md`, `navigation/revit-navigation*.md` | In progress |
| No host (standalone app) | `skills/hosts/none.md` | Built; no host tests |

## 6. Quality
- Unit tests in `CodeBase/tests/` (`uv run pytest`): one test file per module (intake, static read, UI text, Agent 1, self-check, preflight, guardrails, Windows-MCP, UI tree, find-by-name tools, Agent 2, footprint, host, verdict, judge, pipeline) plus a skills genericity check.
- Every LLM request, tool call and model call is traced to `trace.jsonl`; readable log in `run.log`.
