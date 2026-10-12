# Guidance for AI coding agents (Cursor, etc.)

## Read order

1. [docs/SPEC.md](./docs/SPEC.md) — submission contract, tools, outcomes (do not invent tools)
2. [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — orchestrator and run lifecycle
3. [docs/IMPLEMENTATION_PLAN.md](./docs/IMPLEMENTATION_PLAN.md) — current phase; implement incrementally
4. [docs/PLANT3D.md](./docs/PLANT3D.md) — host-specific constraints

Stakeholder narrative: [Autodesk_App_Store_AI_Automated_Validation_Base.docx](./Autodesk_App_Store_AI_Automated_Validation_Base.docx)

## Rules

- **Small increments:** one phase or one tool at a time; do not scaffold the entire platform in one change.
- **Tools execute; LLM plans:** no unrestricted desktop control in agent code paths.
- **Allow-list only:** tools must match [SPEC.md § Tool layer](./docs/SPEC.md#tool-layer) until SPEC is updated.
- **Test data:** use catalogue IDs; do not generate arbitrary DWGs in agent flows.
- **Secrets:** no API keys or license details in repo; use environment variables.
- **Python:** preferred language for orchestrator and tools unless repo later standardizes otherwise.

## PoC trigger

New apps are **submission bundles**, not store scraping. Implement ingest against `submissions/<submission_id>/` first.

## When stuck

- Ambiguous expected behavior → classify **Needs human review** in report, do not fake Pass.
- Plant-specific behavior → update PLANT3D.md and SPEC, then code.
