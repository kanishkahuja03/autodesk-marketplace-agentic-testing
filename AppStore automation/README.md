# AI-Assisted Autodesk App Store Validation (PoC)

Proof-of-concept for an **AI-assisted certification framework** that runs submitted App Store plugins in an isolated **AutoCAD Plant 3D** environment, executes deterministic checks and allow-listed tools, collects evidence, and produces a **reviewer-ready report**. Human reviewers retain final certification authority.

## Authoritative sources

| Document | Role |
|----------|------|
| [Autodesk_App_Store_AI_Automated_Validation_Base.docx](./Autodesk_App_Store_AI_Automated_Validation_Base.docx) | Stakeholder / base specification (vision, options, risks) |
| [docs/SPEC.md](./docs/SPEC.md) | Engineering requirements (contracts, checks, outcomes) |
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Components, flows, run lifecycle |
| [docs/IMPLEMENTATION_PLAN.md](./docs/IMPLEMENTATION_PLAN.md) | Phased delivery and current status |

## Quick links

- [Context & scope](./docs/CONTEXT.md)
- [Plant 3D notes](./docs/PLANT3D.md)
- [Agent / Cursor guidance](./AGENTS.md)

## PoC host product

**AutoCAD Plant 3D** (single version initially—see [PLANT3D.md](./docs/PLANT3D.md)).

## Repository layout (target)

```text
AppStore automation/
├── README.md
├── AGENTS.md
├── docs/
├── submissions/          # PoC: simulated marketplace submissions
├── test_data/            # Approved DWGs, projects, expected outputs
├── src/                  # Orchestrator, tools, agents (to be added)
└── runs/                 # Evidence bundles per certification run (gitignored)
```

## Running locally (when implemented)

Instructions will live here after Phase 0–1 land. Expected shape:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m orchestrator start --submission submissions/<id>
```

## Guiding principle

**AI decides and reasons; deterministic tools execute and verify.** The agent does not receive unrestricted desktop control—only [allow-listed tools](./docs/SPEC.md#tool-layer).
