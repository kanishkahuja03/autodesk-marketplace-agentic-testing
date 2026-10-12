# Context & scope

## Problem

App Store review combines package validation, installation, compatibility, basic stability, functional checks, evidence collection, and human judgement. Much of the **repeatable** work can be standardized; **unknown plugin behavior** cannot be fully inferred without submission artifacts and reviewer-approved expectations.

## What we are building (PoC)

An **assisted validation pipeline** triggered by a **new submission** (production: internal queue/API; PoC: folder drop or manual trigger). For each submission:

1. Route to the correct host environment (**Plant 3D** for this PoC).
2. Install the submitted package.
3. Run **Level 1 generic** checks (no app-specific knowledge).
4. Use AI to propose **app-specific** tests from publisher documentation.
5. Execute only **policy-approved** tool calls.
6. Bundle evidence and classify outcomes: **Pass**, **Fail**, or **Needs human review**.

## What we are not building (initially)

- Universal auto-certification for every App Store app without human review.
- MCP platform for every Autodesk product before tools are proven.
- Fully autonomous approve/reject.
- Public App Store web scraping as the submission trigger.

## Host product: Plant 3D

Revit was replaced with **AutoCAD Plant 3D** for this PoC. Implications: AutoCAD-based automation, DWG/project/spec test data, and product-specific tooling—see [PLANT3D.md](./PLANT3D.md).

## How a “new app” enters the system

The framework does **not** discover listings on the public store. It reacts to a **submission record** containing installer, metadata, and documentation. Every new Plant 3D plugin uses the **same pipeline**; only submission payload and doc-derived tests differ.

## Success (PoC)

Aligned with base specification:

- Repeatable clean Plant 3D environment (provision/reset).
- Automated install and baseline generic checks (target ~80% of selected suite stable over repeat runs).
- AI produces usable test procedures from supplied documentation.
- At least one app-specific workflow with traceable evidence.
- Reviewer can decide from the report without re-running tests.
- Agent cannot invoke actions outside the approved tool boundary.

## Stakeholder positioning

*AI-assisted App Store validation combines deterministic certification checks with AI-generated, application-specific test scenarios. The AI operates through a controlled tool layer in an isolated environment. Human reviewers remain responsible for final certification where behavior cannot be determined automatically.*
