# Architecture Decision Record (ADR) Index

This is an index of the key architecture decisions. ADRs are high-level decisions that affect several modules or the whole pipeline. Low-level design (classes, methods) does not belong here.

Entry formats:
1. `<relative document path>` : short description of the document
2. A short decision, stated directly

Source of truth: [`ARCHITECTURE.md`](ARCHITECTURE.md) (V2.1, 2026-10-12). If an entry here conflicts with it, `ARCHITECTURE.md` wins. Then update this index.

## ADR Index

### Documents
- `./ARCHITECTURE.md` : V2.1 build plan. Decisions D1–D35, the one-F5 flow, agents, preflight, guardrails, cleanup, data contracts, skills, tech stack, code layout, build steps.
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
- **ADR-006 Verdict by code:** Agent 2 reports raw observations only. Code compares them with each test's `expected` checks and sets PASS / FAIL / BLOCKED / ERROR. The LLM never sets a status. *(D7)*
- **ADR-007 Demo scope:** ENV, INST and UNIN tests only. Fully automatic, no human review gate. Demo app: P&ID Connector Exporter. *(D8, D9, D14)*
- **ADR-008 Reuse existing intake:** keep the existing `intake.py` and installer static read (`static_read.py`, `msi.py`). *(D10)*
- **ADR-009 Local tracing only:** OpenAI tracing is disabled. Every LLM turn and MCP call is logged to `trace.jsonl` in the run folder. *(D11)*
- **ADR-010 Execution environment:** the POC runs on the dev machine, elevated. VM or Sandbox isolation is a later phase. *(D12)*
- **ADR-011 Skills as Markdown:** agent instructions and host knowledge are SKILL.md-style Markdown files under `CodeBase/skills/`. OpenAI's hosted Skills API is not used. *(D13)*
- **ADR-012 Host lookup by Agent 1:** the LLM picks a `host_id` from the available host notes, or `none` / `unknown`, and cites its evidence. There is no keyword-matching code. *(D15)*
- **ADR-013 New decisions win:** where `ARCHITECTURE.md` V2 conflicts with older docs or with code already in `CodeBase/`, V2 wins.

### Decisions from the grill-me session (2026-10-12)
- **ADR-014 One Run button:** F5 in Visual Studio always runs the full pipeline into a new run folder. There are no sub-commands and no stop switches. The only launch argument is the input folder `inputs/<app>`. *(D16, D17)*
- **ADR-015 Fail-safe stop before execution:** if Agent 1's plan still fails the self-check after 2 retries, the pipeline stops before Agent 2. It's reported in the logs only. *(D18)*
- **ADR-016 Logging:** each run writes `run.log` (readable, also on the console, final `COMPLETED`/`STOPPED` line) and `trace.jsonl` (all LLM and MCP calls). `report.html` is written only if Agent 2 ran. *(D19)*
- **ADR-017 Code preflight before Agent 2:** the process must be elevated, Windows-MCP must expose exactly the 13 allowed tools, and ENV-000 must show the plug-in isn't installed yet. Any failure → STOPPED. It runs after Agent 1, so Agent 1 stays blind. *(D20)*
- **ADR-018 Windows-MCP installed beforehand:** pinned version, one setup step. F5 only starts it. *(D21)*
- **ADR-019 Built-in ENV-000:** "plug-in not already installed" is a built-in test executed by code. If it fails, INST/UNIN are BLOCKED and nothing is installed. *(D22, D23)*
- **ADR-020 Agent-written tests, code-enforced coverage:** Agent 1 writes all other tests. The self-check requires an install exit-code test, an Uninstall-entry-exists test and an entry-gone test. *(D24)*
- **ADR-021 Gating:** the only hard stops are the preflight checks. Other dependencies are per-test preconditions, applied afterwards by the verdict engine as BLOCKED. Agent 2 runs every test. *(D25)*
- **ADR-022 Install and uninstall paths:** install silently with msiexec + verbose log; uninstall through the Windows UI via Windows-MCP. *(D26, D27)*
- **ADR-023 Cleanup in code:** a `finally` step runs `msiexec /x` only if the plug-in is still installed and UNIN didn't complete. It never changes a verdict. *(D28)*
- **ADR-024 Time limits:** Agent 2 gets 150 turns, 120 s per tool call and 20 min in total (configurable). A limit hit → missing tests ERROR + cleanup. *(D29)*
- **ADR-025 Incremental observations:** Agent 2 reports each test immediately through the local `record_observation` tool into `observations.json`. Our hook saves screenshots to `evidence/`. *(D30, D31)*
- **ADR-026 Guardrails in code:** PowerShell commands must start with an allow-listed command. Registry is read-only. FileSystem writes only in the run folder, never deletes. *(D32, D33)*
- **ADR-027 One model setting:** both agents use `OPENAI_MODEL`. *(D34)*
- **ADR-028 Run result:** exit code 0 = completed (even with FAIL tests), 1 = stopped, 2 = crash. *(D35)*
