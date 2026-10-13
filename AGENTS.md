# Instructions for Coding Agents: Marketplace App Validation Agents

## About this project
A generic two-agent pipeline that validates Windows desktop plug-ins and standalone apps from their documentation and installer.
- **Agent 1** designs cited test cases (`testcases.yaml`) without touching the machine.
- **Agent 2** runs them through Windows-MCP.
- Code decides PASS or FAIL from the observed values and writes a report with evidence.

Built with Python 3.12, uv, the OpenAI Agents SDK and Windows-MCP. AutoCAD Plant 3D 2027 is the first host.

## Required reading before making any changes
1. [`ARCHITECTURE.md`](ARCHITECTURE.md): the V2 build plan. It is the source of truth.
2. [`ADR.md`](ADR.md): architecture decisions. Do not implement anything that conflicts with them.
3. [`AGENT_TOOLING_REVIEW.md`](AGENT_TOOLING_REVIEW.md): tool lists for both agents (under team review).
4. [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md): background. Parts are outdated (Gemini, pywinauto/Robot). Where it conflicts with `ARCHITECTURE.md`, follow `ARCHITECTURE.md`.
5. Skill files in `.agents/skills/` (mirrored in `.claude/skills/` for Claude Code).

## Working rules
- Make small, focused changes. Prefer the minimal change that meets the request.
- When unsure, **ask instead of guessing**, and briefly state the trade-offs.
- Follow existing project patterns (Pydantic models in `models.py`, Typer CLI, uv) before introducing new ones.
- Do not modify docs (`*.md` at the repo root, `AppStore automation/`) unless the user explicitly asks.
- Add folders only when something is actually built in them. No empty scaffolding.
- Secrets (`OPENAI_API_KEY` etc.) only in `CodeBase/.env`, never in code or docs.
- Add dependencies with `uv add <name>` from `CodeBase/`, so `uv.lock` stays in sync.
- Run `uv run pytest` from `CodeBase/` after code changes. All tests must pass.
- Keep the design/execution boundary: nothing in `src/mpagent/design/` imports from `src/mpagent/execute/`.
- When a skill is changed, update both copies (`.agents/skills/` and `.claude/skills/`) so they stay identical.

## Project folder map
- `.agents/skills/` : agent skills (canonical copy), e.g. `grill-me/`
- `.claude/skills/` : identical copy of the skills, so Claude Code can find them
- `ARCHITECTURE.md`, `ADR.md` : current architecture and decisions
- `ARCHITECTURE_old1.md` : superseded v0.3 design (reference only)
- `AGENT_TOOLING_REVIEW.md`, `ARCHITECTURE_COMPARISON.md`, `DESKTOP_UI_AUTOMATION_RESEARCH.md`, `AGENT_FUNDAMENTALS.md`, `PROBLEM_STATEMENT.md` : supporting docs
- `AppStore automation/` : the alternative design that was compared. Reference only, do not build there.
- `CodeBase/` : the product (Python package `mpagent`)
  - `src/mpagent/` : source (`cli.py` single entry point, `pipeline.py` step order; `design/` = S0, S1 and Agent 1; `execute/` = preflight, guardrails, Agent 2, cleanup, verdict and report)
  - `skills/` : runtime skills loaded into the agents (`test-design/`, `hosts/`, `execute/`; see ARCHITECTURE.md §7)
  - `tests/` : pytest unit tests
  - `inputs/<app>/` : third-party input files (git-ignored)
  - `runs/<app>/<timestamp>/` : run outputs and evidence (git-ignored)
