# Architecture Comparison: Our Approach vs "AppStore automation"

**Date:** 2026-10-12
**Compared:**
- **Approach A (ours):** [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md), [`ARCHITECTURE.md`](ARCHITECTURE.md) v0.3, plus the partially built `CodeBase/`.
- **Approach B (alternative):** [`AppStore automation/`](AppStore%20automation/README.md): `Autodesk_App_Store_AI_Automated_Validation_Base.docx` (stakeholder base spec), plus `docs/SPEC.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `PLANT3D.md` and `IMPLEMENTATION_PLAN.md`. Status: docs only (Phase 0).

> Note: the base `.docx` still names **Revit** as the host. B's `docs/CONTEXT.md` says it was replaced with **Plant 3D**.

---

## 1. One-line summary

| | Approach A (ours) | Approach B (AppStore automation) |
|---|---|---|
| **Core idea** | **Two agents, split by time.** Agent 1 designs a complete, cited test plan (YAML) from the inputs alone, with no machine access. Agent 2 runs it deterministically. | **One orchestrated run.** A fixed generic suite runs first, then an AI agent plans app-specific tests *after install*. A policy gate approves them, they run through allow-listed tools, and a human reviewer decides. |
| **Guiding rule** | "LLM only produces data; code decides pass or fail." | "AI decides and reasons; deterministic tools execute and verify." |

Both agree on the essentials: the LLM never gets free control of the desktop, actions come from an allow-list, results carry evidence, the code is Python, Plant 3D is the first host, and MCP is not a first objective.

---

## 2. Side-by-side

| Dimension | A (ours) | B (AppStore automation) |
|---|---|---|
| **Trigger and inputs** | Unstructured folder `inputs/<plugin>/`: any docs, the installer, optional `metadata.json` scraped from the Marketplace | Structured **submission bundle** `submissions/<id>/`: `metadata.json` with `host_versions`, `package/`, `docs/`, optional **`publisher_test_notes`** |
| **When the AI plans** | **Before** anything touches the machine (Agent 1) | **After** install and the generic suite, so the agent sees the generic results |
| **Generic checks** | ENV / INST / UNIN test cases written by Agent 1 for each plug-in | **Level 1 suite**: a fixed pytest suite, no LLM, the same for every submission |
| **Host-specific capability** | Host profiles (YAML data) plus `host.*` actions; generic for **any host, including non-Autodesk** | **Level 2** reusable Plant 3D tools, added only when needed; one host for now |
| **App-specific tests** | Agent 1 designs LOAD / FUNC from the docs, with source citations | **Level 3**: the agent proposes, the policy gate validates, the tools execute |
| **Plan artifact** | `understanding.md` + `testcases.yaml`, which a person can review and version, with source quotes checked by substring match | JSON test plan checked by the policy gate; `agent_trace.jsonl` |
| **Approval before execution** | Optional **human review gate** (`--approve` / `--auto`) | **Automatic policy gate** (tools, paths, dataset IDs); human only at the end |
| **Tool / action layer** | Action catalog of about 30 actions across `sys.*`, `snap.*`, `host.*`, `ui.*` (click, element_exists) and `cp.*` | About 13 allow-listed tools; **no direct keyboard or mouse** in SPEC; prefers `run_command` over UI |
| **Test data** | `test_assets/` mentioned as a precondition only | **Curated test data catalogue** with dataset IDs; the AI may only choose catalogued IDs |
| **Environment discovery** | E1: inventory, host resolution (profile, or AI in the loop), `env.json`, placeholders | Assumes a **known VM template**; the analyzer selects the template |
| **Clean state** | POC: scripted cleanup + **file and registry snapshot diff**; Hyper-V later | **VM snapshot restore** from the start (or a cleanup script) |
| **Outcomes** | PASS / FAIL / BLOCKED / NOT_APPLICABLE / ERROR | Pass / Fail / **Needs human review** |
| **Who decides the verdict** | Code only | Deterministic checks. The `.docx` also says the "AI … classifies the outcome", and a **human reviewer** makes the final decision |
| **Isolation and safety** | This machine for now (risk accepted), signature check first | Isolated VM, sandbox paths, no shell or network |
| **Maturity** | Detailed design, verified Plant 3D facts and risks (UAC, SECURELOAD, ribbon), some `CodeBase/` runs | High-level phased plan, Phase 0, Plant 3D version and pilot plug-ins still TBD |

---

## 3. Approach A (ours): pros and cons

### Pros
1. **Strong protection against invented facts.** Every test cites a source line, the citations are checked by substring match, unknown fields stay `null`, and a self-check loop catches errors.
2. **A clean design/run boundary.** This meets the hard rule from our superiors (no machine inspection in Agent 1). The design side runs on any machine.
3. **A reviewable, versionable test plan.** `testcases.yaml` is readable, works with git diffs, is not tied to pywinauto or Robot, and can become a **golden plan** that re-runs without the LLM.
4. **Generic across hosts.** Host profiles keep host-specific knowledge as data, AI-assisted discovery handles new hosts, and standalone apps are covered (`host_id: none`).
5. **Richer outcome statuses.** `BLOCKED` and `NOT_APPLICABLE` separate "the plug-in failed" from "the environment couldn't run the test".
6. **Install footprint checked by snapshot diff.** This catches leftovers after uninstall and finds where the plug-in really installed.
7. **More concrete.** It is grounded in Plant 3D 2027 details and has a 17-item risk list and an exact action catalog. Some code exists already.

### Cons
1. **Agent 1 plans blind.** It can't adapt to what the machine or the generic results show, so it relies on placeholders and `BLOCKED` / `NOT_APPLICABLE` statuses. The feedback loop is deferred.
2. **Generic checks are regenerated by the LLM for every plug-in.** Tests that are the same every time (install exit code, Programs and Features entry, uninstall) cost tokens and can vary between runs, where a fixed suite would be stable.
3. **No formal test data catalogue.** FUNC tests (e.g. "Export needs an open P&ID drawing") have no governed dataset to draw on.
4. **No "Needs human review" outcome.** Functional results that can't be checked automatically get forced into PASS or FAIL.
5. **The UI layer is more exposed.** The `ui.click` and `cp.*` Control Panel uninstall paths bring UAC and fragility problems (§11 #1, #4).
6. **Weaker isolation for the POC.** Untrusted installers run on the dev machine.
7. **Broader scope** (any host, non-Autodesk) adds design weight that a Plant 3D POC doesn't need yet.

---

## 4. Approach B (AppStore automation): pros and cons

### Pros
1. **Matches the stakeholder base document and client positioning.** The flow is submission, report, human reviewer, which is how App Store review actually works.
2. **Deterministic Level 1 suite.** It is the same for every submission, needs no LLM, is cheap, repeatable and easy to trust, and B targets about 80% of it stable over repeat runs.
3. **The AI plans with real context.** It sees the generic results and the installed state, can skip Level 3 if Level 1 fails, and has fewer blind placeholders.
4. **Explicit policy gate.** Tools, paths and dataset IDs are validated in code before execution, a clear safety component.
5. **Curated test data catalogue.** FUNC tests are meaningful and repeatable, and the AI can't invent files.
6. **Honest "Needs human review" outcome** for results that can't be checked automatically.
7. **Prefers commands and APIs over UI** (`run_command`, `wait_for_idle`). This is more robust on AutoCAD's ribbon and command line.
8. **Isolation from the start** (VM snapshot, no shell or network) and a clearer security posture.
9. **A structured submission contract**, including `publisher_test_notes`, which is a valuable source of expected behaviour.

### Cons
1. **Only at the documentation stage.** The Plant 3D version and pilot plug-ins are TBD. Many Plant 3D facts and risks are still open (A has already researched them).
2. **Weaker controls against invented facts in planning.** There are no source citations or quote checks. The policy gate checks that a plan *can be executed*, not that it is *true to the docs*.
3. **The verdict is partly left to the AI.** The `.docx` has the AI "interpret results" and "classify the outcome". That is less auditable than A's "code decides" rule, though the human reviewer makes up for it.
4. **No human review of the plan before execution.** The policy gate is automatic, and humans only see the final report.
5. **Planning needs the machine.** Plans are made mid-run, so there is no standalone plan artifact to review, version or re-run as a golden plan. That conflicts with our "Agent 1 only designs" rule.
6. **Tied to one host.** It assumes a known VM template, with no environment discovery and no generic host profiles. A new host means new Level 2 tools in code.
7. **A small allow-list (13 tools) without UI primitives** in SPEC. LOAD checks such as "ribbon tab present" and UI-only plug-ins may not be testable until UI tools are added (the `.docx` lists `find_element` / `click`, SPEC does not).
8. **No snapshot diff for uninstall leftovers.** Checking for a clean removal is weaker.
9. **Setup cost up front.** It needs a VM with licensed Plant 3D (licensing inside a VM is a known risk) and a curated dataset before anything runs.

---

## 5. Where they really conflict

| Conflict | A | B | Note |
|---|---|---|---|
| **When the AI plans** | Before any machine access | After install and generic checks | A follows a **hard boundary from our superiors**. Adopting B's model would need their sign-off. |
| **Who approves the plan** | A human, optionally, before execution | Code (policy gate) before, a human after | They can be combined: code gate + optional human gate. |
| **The AI's role in the verdict** | None | Interprets results and classifies outcomes (per the `.docx`) | Middle ground: code decides Pass/Fail, and the AI may only *propose* "Needs human review". |
| **How generic the scope is** | Any host | One host, add adapters when proven | A's generality is a design property. B is the more pragmatic place to start. |

---

## 6. Suggested synthesis (for discussion)

Keep A's backbone (the Agent 1/Agent 2 split, cited YAML plans, host profiles, code-decided verdicts) and adopt from B:

1. **A fixed Level 1 suite.** Make the ENV / INST / UNIN core a deterministic, non-LLM suite run for every plug-in. Agent 1 then focuses on LOAD / FUNC (Level 3) plus plug-in-specific install expectations.
2. **A test data catalogue** with dataset IDs. Agent 1 may only reference catalogued datasets, and the self-check rejects unknown IDs.
3. **A `NEEDS_REVIEW` status** alongside A's statuses, for results that can't be verified automatically.
4. **A policy gate as an explicit step.** A's self-check (1d) is already most of this. Run it again on the approved YAML just before Agent 2 executes.
5. **Submission contract fields:** add `host_versions` and `publisher_test_notes` to the intake. Notes become citable sources.
6. **Prefer `host.run_command` over `ui.click`** for driving the host. Keep UI actions for presence checks (ribbon tab) and gaps, with screenshots.
7. **Reviewer-ready report framing** (human final decision), to match the stakeholder positioning.
8. **VM snapshot isolation** brought forward as soon as the POC demo is done.

Open decision: B's "plan after generic results" model conflicts with A's boundary. A possible compromise is A's planned feedback loop (Later phases #5): Agent 2's ENV and Level 1 findings go back to Agent 1 for a *second* design pass, so planning stays separate from running.
