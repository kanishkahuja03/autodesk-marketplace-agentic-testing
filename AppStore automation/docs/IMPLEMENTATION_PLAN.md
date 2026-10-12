# Implementation plan

Living delivery plan. Update status as phases complete.

**Approach:** Option B (AI + controlled automation) evolving toward Option D (MCP + hybrid). See base `.docx` section 12–13.

## Phase status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repo structure, docs, config, `.gitignore`, PoC README run section | In progress |
| 1 | Environment controller: Plant 3D launch/close, golden DWG open | Not started |
| 2 | Tool layer v1 + unit tests per tool | Not started |
| 3 | Generic (Level 1) runner wired to tools | Not started |
| 4 | Submission folder ingest + analyzer | Not started |
| 5 | LLM agent: plan JSON + policy gate + execute | Not started |
| 6 | Evidence bundle + HTML report | Not started |
| 7 | One app-specific workflow per pilot plugin | Not started |
| 8 | (Optional) MCP facade over tools | Not started |

## Phase 0 — Done when

- [x] `README.md`, `docs/*`, `AGENTS.md`
- [ ] `requirements.txt`, `pyproject.toml` or equivalent
- [ ] `submissions/` and `test_data/` placeholders
- [ ] `.gitignore` for `runs/`, `.venv`, secrets

## Phase 1 — Environment

- Secure Windows VM with licensed Plant 3D (version TBD).
- Document snapshot/reset in [PLANT3D.md](./PLANT3D.md).
- Script: install pilot plugin from submission package.

## Phase 2 — Tools

Implement [SPEC tool allow-list](./SPEC.md#tool-layer) in small modules; each tool has a standalone smoke test on VM.

## Phase 3 — Generic suite

- pytest suite calling tools only (no LLM).
- Target: 5–10 checks stable across 3 consecutive runs.

## Phase 4 — Ingest

- `metadata.json` schema validated.
- `python -m orchestrator start --submission submissions/<id>` creates `runs/<run_id>/`.

## Phase 5 — Agent

- Prompt + structured output schema for test plans.
- Policy gate rejects invalid tools/paths/datasets.
- Trace logged to `agent_trace.jsonl`.

## Phase 6 — Report

- Single HTML report: generic table, app-specific section, screenshots, Pass/Fail/Needs review.

## Phase 7 — Pilot apps

- With review SME: pick 1–2 plugins, 1–3 workflows, deterministic checks where possible.

## Immediate next steps

1. Interview review team: common checks for Plant 3D submissions.
2. Name Plant 3D version and 1–2 pilot plugins.
3. Collect installer, docs, and reviewer test notes for pilot `submission_id`.
4. Stand up VM and golden test data (see PLANT3D.md).
5. Implement `launch_application`, `open_drawing`, `capture_screenshot`.

## Decision questions (PoC exit)

1. Can we reliably prepare clean Plant 3D + plugin?
2. Can AI turn docs into safe, useful tool sequences?
3. Are results observable enough for Pass/Fail, with human review otherwise?

## Risks (track here)

| Risk | Mitigation |
|------|------------|
| UI automation flake | Prefer commands/API; short waits |
| No deterministic expected result | Needs human review status |
| Licensing blocks automation | Validate early on VM |
| Weak Plant 3D test data | SME-curated catalogue |
