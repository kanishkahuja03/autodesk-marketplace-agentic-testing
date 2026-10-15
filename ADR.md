# Architecture Decision Record (ADR) Index

This is an index of the key architecture decisions. ADRs are high-level decisions that affect several modules or the whole pipeline. Low-level design (classes, methods) does not belong here.

Entry formats:
1. `<relative document path>` : short description of the document
2. A short decision, stated directly

Source of truth: [`ARCHITECTURE.md`](ARCHITECTURE.md) (V2.3, 2026-10-13). If an entry here conflicts with it, `ARCHITECTURE.md` wins. Then update this index.

## ADR Index

### Documents
- `./ARCHITECTURE.md` : V2.3 build plan. Decisions D1–D67, the one-F5 flow, agents, preflight, guardrails, cleanup, data contracts, skills, tech stack, code layout, build steps.
- `./FUNC_TESTS_PLAN.md` : draft plan for FUNC tests (running documented features), decisions F1–F16; not yet agreed.
- `./LOAD_TESTS_PLAN.md` : the LOAD test plan (formerly FUNCTIONAL_TESTS_PLAN.md): decisions L1–L29 behind D40–D67, the current design, and the live runs; built and verified 2026-10-14 (14 PASS with generic skills).
- `./AGENT_TOOLING_REVIEW.md` : Agent 1 components and Agent 2 Windows-MCP tools, one by one, with keep/drop recommendations for team review.
- `./ARCHITECTURE_COMPARISON.md` : Our approach vs the `AppStore automation/` approach. Pros and cons, and what V2 took from each.
- `./DESKTOP_UI_AUTOMATION_RESEARCH.md` : Research on desktop UI automation MCP servers, models and libraries.
- `./ARCHITECTURE_old1.md` : Superseded v0.3 design. Kept for its reasoning only.

### Decisions (2026-10-12 unless noted)
- **ADR-001 Generic scope:** the pipeline validates any Windows desktop plug-in or standalone app. Host-specific knowledge lives only in host-notes skill files. AutoCAD Plant 3D 2027 is the first host. *(ARCHITECTURE.md D1)*
- **ADR-002 Two agents, split by time:** Agent 1 designs the tests and Agent 2 runs them. Agent 1 is blind: no tools, no machine access, single pass. This is a hard boundary set by management (2026-10-08). *(D4)*
- **ADR-003 LLM provider:** enterprise OpenAI API, with the model name set in `.env`. Gemini dropped. Cost is not a constraint for the POC. *(D2)*
- **ADR-004 Agent framework:** OpenAI Agents SDK (Python). It supplies the agent loop, MCP client, structured output and tool filtering. *(D3)*
- **ADR-005 Machine interaction:** Agent 2 drives the machine only through Windows-MCP (UI, Registry, FileSystem, Process, PowerShell), using a 13-tool allow-list enforced in two places. There is no action catalogue of our own. The one local tool is `record_observation` (ADR-025), which only writes a file. *(D5, D6)*
- **ADR-006 Verdict by code:** Agent 2 reports raw observations only. Code compares them with each test's `expected` checks and sets PASS / FAIL / NEEDS_REVIEW / BLOCKED / ERROR. *Updated 2026-10-14:* claims about what the UI shows are decided by an evidence-bound LLM judge instead (ADR-041). The LLM never sets a status. *(D7)*
- **ADR-007 Demo scope:** ENV, INST, LOAD and UNIN tests (LOAD added 2026-10-13, ADR-033). Fully automatic except one y/n review of the test cases (ADR-040). Demo app: P&ID Connector Exporter. *(D8, D9, D14)*
- **ADR-008 Reuse existing intake:** keep the existing `intake.py` and installer static read (`static_read.py`, `msi.py`). *(D10)*
- **ADR-009 Local tracing only:** OpenAI tracing is disabled. Every LLM turn and MCP call is logged to `trace.jsonl` in the run folder. *(D11)*
- **ADR-010 Execution environment:** the POC runs on the dev machine, elevated. VM or Sandbox isolation is a later phase. *(D12)*
- **ADR-011 Skills as Markdown:** agent instructions and host knowledge are SKILL.md-style Markdown files under `CodeBase/skills/`. OpenAI's hosted Skills API is not used. *(D13)*
- **ADR-012 Host lookup by Agent 1:** the LLM picks a `host_id` from the available host notes, or `none` / `unknown`, and cites its evidence. There is no keyword-matching code. *(D15)*
- **ADR-013 New decisions win:** where `ARCHITECTURE.md` V2 conflicts with older docs or with code already in `CodeBase/`, V2 wins.

### Decisions from the grill-me session (2026-10-12)
- **ADR-014 One Run button:** F5 in Visual Studio always runs the full pipeline into a new run folder. There are no sub-commands and no stop switches; the only question asked is the test-case review (ADR-040). The only launch argument is the input folder `inputs/<app>`. *(D16, D17)*
- **ADR-015 Fail-safe stop before execution:** if Agent 1's plan still fails the self-check after 2 retries, the pipeline stops before Agent 2. It's reported in the logs only. *(D18)*
- **ADR-016 Logging:** each run writes `run.log` (readable, also on the console, final `COMPLETED`/`STOPPED` line) and `trace.jsonl` (all LLM and MCP calls). `report.html` is written only if Agent 2 ran. *(D19)*
- **ADR-017 Code preflight before Agent 2:** the process must be elevated, Windows-MCP must expose exactly the 13 allowed tools, and ENV-000 must show the plug-in isn't installed yet. Any failure → STOPPED. It runs after Agent 1, so Agent 1 stays blind. *(D20)*
- **ADR-018 Windows-MCP installed beforehand:** pinned version, one setup step. F5 only starts it. *(D21)*
- **ADR-019 Built-in ENV-000:** "plug-in not already installed" is a built-in test executed by code. If it fails, INST/UNIN are BLOCKED and nothing is installed. *(D22, D23)*
- **ADR-020 Agent-written tests, code-enforced coverage:** Agent 1 writes all other tests. The self-check requires an install exit-code test, an Uninstall-entry-exists test and an entry-gone test, and rejects ENV tests that observe the app's installation keys. *(D24)*
- **ADR-021 Gating:** the only hard stops are the preflight checks. Other dependencies are per-test preconditions, applied afterwards by the verdict engine as BLOCKED. Agent 2 runs every test. *(D25)*
- **ADR-022 Install and uninstall paths:** install **and uninstall silently** with msiexec + verbose logs (`install.log`, `uninstall.log`). Code creates `evidence\` before Agent 2; both exit codes are read from the logs, never from PowerShell's status code. *(D26, D27; the Programs and Features UI uninstall was dropped on 2026-10-13 after a wrong-program selection.)*
- **ADR-023 Cleanup in code:** a `finally` step runs `msiexec /x` only if the plug-in is still installed and UNIN didn't complete. It never changes a verdict. *(D28)*
- **ADR-024 Time limits:** Agent 2 gets 150 turns, 120 s per tool call and 40 min in total (configurable; raised from 20 for LOAD). A limit hit → missing tests ERROR + cleanup. *(D29)*
- **ADR-025 Incremental observations:** Agent 2 reports each test immediately through the local `record_observation` tool into `observations.json`. Our hook saves screenshots to `evidence/` and attaches them to the next `record_observation` automatically. Evidence files that don't exist are rejected; an executed observation is never replaced by a not-executed one. *(D30, D31)*
- **ADR-026 Guardrails in code:** PowerShell commands must start with an allow-listed command (msiexec via `Start-Process -FilePath msiexec.exe … -Wait`; `Select-String` for reading logs; no `;`, script blocks, subexpressions, redirection or line breaks, and no `&` outside quotes). Registry is read-only. **FileSystem is read-only**, and whole-file reads over 50 KB need `offset`/`limit`. *(D32, D33)*
- **ADR-027 One model setting:** both agents use `OPENAI_MODEL`. *(D34)*
- **ADR-028 Run result:** exit code 0 = completed (even with FAIL tests), 1 = stopped, 2 = crash. *(D35)*

### Decisions from live runs (2026-10-13)
- **ADR-029 Per-run guardrail rules:** a second `msiexec /i` is rejected, and the same tool call with the same arguments more than 3 times is rejected (looking-again tools exempt). *(D36)*
- **ADR-030 Cleaned, capped tool results:** PowerShell CLIXML noise is removed (errors decoded) and results over 20,000 characters are cut off before the model sees them; the original goes to the trace. *(D37)*
- **ADR-031 App facts for Agent 2:** code passes DisplayName, ProductCode, the Uninstall registry paths, expanded install roots and the machine's real folders, so Agent 2 never guesses names or paths. *(D38)*
- **ADR-032 Stopping a run:** Ctrl+C lets cleanup and the report run; the VS Stop button kills the process, and the next run's ENV-000 prints the exact uninstall command. *(D39)*

### Decisions from the LOAD grill-me review (2026-10-13)
- **ADR-033 LOAD tests:** the host starts with its default new document (built-in LOAD-000, written by code), and the app's documented entry point label is visible (exactly one agent test, LOAD-001, required for ribbon tabs, menus, toolbars). App-specific documents are FUNC (later). *(D40–D42)*
- **ADR-034 Host facts in host notes:** `host_process` front matter (registry lookup, exe, exact args, processes, title regexes) is the only place host facts for code live. *(D43)*
- **ADR-035 UI verdicts from the raw UI tree:** `window_in_ui` / `seen_in_ui` are decided by code from the full Snapshot text, only inside the host's main window, exact element names; NEEDS_REVIEW when only a screenshot could tell. *(D44–D46)*
- **ADR-036 Host safety:** one Agent 2 session; App starts only the host with its exact args; no uninstall while the host runs; host closed by Process kill; preflight stops if the host already runs; `finally` kills the host before cleanup. *(D47–D52)*
- **ADR-037 Order and crashes enforced by code:** no host start before the installer ran; no executed install test without it; a host crash gets one restart, and code saves Windows' crash records for the host to the evidence and the report. *(D53, D54)*
- **ADR-038 Normal environment for Windows-MCP:** the server (and every program it starts) gets the normal Windows environment without secrets, not the MCP SDK's 12-variable default; that default made Plant 3D crash at every pipeline start. *(D55)*

### Decisions from 2026-10-14
- **ADR-039 Dialogs decided by Agent 2:** Agent 2 judges each dialog (notice, load prompt, error, crash, lasting change, unclear) and picks the button with the smallest lasting effect; never "Always …" or settings changes. Evidence = the attached screenshots; the record = the LOAD test's `notes`. No extra guardrail or file. Replaces the blanket "stop at any other dialog" rule. *(D56, replaces D49)*
- **ADR-040 Test-case review in the console:** after Agent 1, the console lists the test cases and asks y/n before anything touches the machine; `n` stops the run. No console → the run continues. Requested by the seniors for the recorded demo. *(D57, updates D9, D16)*
- **ADR-041 LLM judge for UI claims:** a separate, fresh model call (same `OPENAI_MODEL`) decides whether a documented UI claim holds, from the test's screenshots, Snapshot text and Agent 2's notes. Agent 2 never grades its own work; facts stay with code. *(D58, D7; built 2026-10-14)*
- **ADR-042 Claims and the app's own UI text:** UI tests carry the documented claim (`judged`), not an expected string; LOAD-001 (entry point) and LOAD-002 (its items). S1 extracts the app's own UI text from the installer's binaries as citable source `U1`. Matching only `U1` = PASS with a "documentation mismatch" finding. *(D59–D61; built 2026-10-14)*
- **ADR-043 Generic exploration and findings:** Agent 2 opens only what reveals UI, never what acts, with screenshots and notes; the report shows each judgement and a Findings section. *(D62, D63; built 2026-10-14)*
- **ADR-044 Nothing left behind:** a built-in UNIN-000 compares the machine before the install with the state after the uninstall (registry Software keys, user/data/program folders, install roots). Program leftovers FAIL; leftover user settings are PASS with a finding. Code reports, never deletes. *(D64)*
- **ADR-045 Covered UI and the judge's client:** Agent 2 uncovers the claimed UI with view-only, undone changes; the judge treats covered elements as NEEDS_REVIEW ("hidden is not missing"). The judge uses its own OpenAI client and event loop per call. *(D65, D66)*
- **ADR-046 Generic skills, host knowledge as data:** skills hold principles only; a host profile is front matter only (`host_process`, `releases`). Run 20261014-175347 with generic skills matched the case-tuned run (14 PASS, same findings, faster). Requires a strong model (gpt-5.5 class). *(D67)*
