# Plan: FUNC tests (does the app's documented feature work?), generic

> **Status:** draft v2 for a grill-me review, 2026-10-14 (v2: no cap on FUNC tests, no fixed test shapes; F1, F13 changed, F14–F16 new). Builds on [`ARCHITECTURE.md`](ARCHITECTURE.md) (D1–D67), [`LOAD_TESTS_PLAN.md`](LOAD_TESTS_PLAN.md) (LOAD, L1–L29) and [`ADR.md`](ADR.md). Once agreed, the decisions in §3 become ARCHITECTURE.md D68+ and ADR entries.
> **Rule kept from D1/D67:** nothing in the code or the skills names a product. App knowledge comes from the app's documents and files (D*, I*, U1, F1); host knowledge only from the host profile's **front matter** (data). The example below (the P&ID Connector Exporter) is only an example.

---

## 1. Goal

Today a run tests **ENV → INST → LOAD → UNIN** (14 PASS with generic skills, runs 20261014-175347 and -194215). FUNC adds one category between LOAD and UNIN: **run a feature the documents describe, the way a user would, and check its result.**

```
ENV → INST → LOAD (entry point present) → FUNC (prepare context → run feature → check result) → kill host → UNIN
```

| FUNC checks (generic) | Example for the P&ID Connector Exporter (derived, not hard-coded) |
|---|---|
| The context the documents require can be set up without touching the user's data | D2: "the user must be in a P&ID project and have a drawing open" → a P&ID drawing inside a **copy** of an empty project in the run's sandbox |
| The documented feature can be started from its entry point | D2: "The 'Export' button is used to export the entire drawing to a JSON file" → Tools → "Export P&ID" |
| It produces the documented result | a JSON file, saved into the sandbox output folder |
| The result matches what the documents say about it | D2: "assets and lines, as well as all associated P&ID properties…" → the judge compares the file's content with the claim |

**Demo acceptance:** one F5 run on the P&ID Exporter gives a FUNC result with evidence (screenshots of each step, the output file), the host is killed, and UNIN still runs and passes. The other 14 tests are unchanged.

**Out of scope (later):** features that need another product or service (here: the Revit Importer), network or account actions, features that change the host's settings, standalone apps (`host: none`, see §8), EXE installers.

---

## 2. What already exists and is reused

| Need | Already built |
|---|---|
| Claims from the documents, cited and quote-checked | Agent 1 + self-check (`judged` claims, D59) |
| The app's own words (labels, messages) | `U1` (D60) |
| UI driving with generic principles | Agent 2 + Windows-MCP, `host-interaction.md` (D56, D62, D65, D67) |
| Evidence and a reviewer for UI and content claims | screenshots + the LLM judge with code guards (D58, D61, D66) |
| Facts decided by code | the verdict engine (D7), `window_in_ui`, UNIN-000 |
| Host data | the host profile's front matter (`host_process`, `releases`) |

FUNC adds **four** generic things: a context in a sandbox, a narrow permission to act, an output folder, and output checks.

---

## 3. Decisions to grill (each with a recommendation)

| # | Question | Options | Recommendation |
|---|---|---|---|
| F1 | Which features become tests? | (a) **every documented feature whose result the documents describe**, as many as the documents give · (b) a fixed number · (c) a human picks | **(a)**: no limit. Each test cites the feature and the result it claims. Features Agent 1 can't test safely (they need another product, a network, an account, or change the host's settings) → an **open question with the reason**, no test. Features seen only in the app's own text (`U1`) but not described in the documents → an open question ("undocumented feature"), no test: there is no documented result to check |
| F2 | Where does the feature's **context** (a document of a certain kind, a project) come from? | (a) **a template the host profile names, copied by code into the run's sandbox** · (b) Agent 2 creates it through the UI from nothing · (c) a curated test-data catalogue in the repo · (d) the user's own files | **(a) for the container + (b) for the content**: code copies the host's empty template (e.g. a project skeleton) into `runs/<run>/sandbox/`; Agent 2 creates the document inside it through the UI, as a user would. Nothing outside the sandbox is touched. (c) later, for features that need real data. Never (d) |
| F3 | How does the host profile describe contexts? | (a) **front matter `contexts:`** (name, template folder to copy, how to open it: launch argument or "open the file") · (b) prose | **(a)**: data, like `host_process`; Agent 1 maps the documents' `use_context` to a context name from the catalogue, or raises an open question |
| F4 | How much may Agent 2 **act** in FUNC? | (a) **only the feature the test names**, plus what that feature itself asks (its own dialogs) · (b) anything in the app | **(a)**: "reveal, never act" stays for everything else (D62). The test's claim names the feature; acting on anything else is a deviation to record |
| F5 | Where do outputs go? | (a) **only into `sandbox/output/`, given by code in the input** · (b) wherever the app suggests | **(a)**: in a save dialog Agent 2 types the given output path. A guardrail rejects typing an absolute path outside the sandbox (generic: it only compares paths) |
| F6 | Who decides the result? | (a) **code for file facts + the judge for UI and content claims** · (b) only the judge · (c) only code | **(a)**: code finds the files **created in `sandbox/output/` during the test** (no need to trust Agent 2's word) and checks them (`file_created`, `file_not_empty`, `json_valid` / `xml_valid`); the judge decides the claims ("a dialog confirms the export", "contains assets and lines") from screenshots **and the file's content** (capped excerpt) |
| F7 | New checks | `output_created`, `output_valid`, `judged` (exists) | **Two code checks + `judged`**, all generic: `output_created` = a new, non-empty file in `output/`; `output_valid` = the file parses, for formats code can parse in a standard way (e.g. structured text formats); for other formats it is not used and the judge reads what it can. No content check by string matching |
| F8 | Preconditions | (a) **LOAD-000** (host + a document) · (b) LOAD-001 (entry point present) too | **(a)**: a NEEDS_REVIEW on LOAD-001 must not block FUNC (open point from Q6). Agent 2 finds the entry point itself; the judge sees the steps |
| F9 | Order inside Agent 2's session | (a) **after LOAD, same host session, then kill the host** · (b) restart the host for FUNC | **(a)**: open the sandbox context in the running host; if the context needs a fresh start (host profile says so), restart once |
| F10 | Time limit | keep 40 min · raise | **Keep 40 min** for now (runs take ~8 min); revisit after the first FUNC run |
| F11 | Cleanup | (a) **the sandbox lives in the run folder** and is kept as evidence; the host's own traces (recent files, project list) are host churn · (b) code deletes the sandbox | **(a)**: nothing to delete outside the run folder; UNIN-000 ignores the run folder and the host's `profile_ignore` |
| F12 | Language of the app | (a) **generic**: the claim keeps the documents' words; Agent 2 and the judge read whatever language the app shows | **(a)**: run 20261014-194215 showed a German UI handled without hints |
| F13 | How many tests, in which order? | (a) **no limit; the documents decide** · (b) a cap | **(a)**: Agent 1 writes one test per documented result it can cite, and orders them so that features that only show something run before features that write files. Code scales Agent 2's time limit with the number of FUNC tests (F15) instead of capping the tests |
| F14 | Test shapes | (a) **generic rules for every FUNC test** · (b) fixed roles per test ID (like LOAD-001 "entry point", LOAD-002 "items") | **(a)**: the skill and the self-check describe what *any* FUNC test needs: a cited feature, the context it needs, a claim of its documented result in the documents' words, and, when the documents name a file result, the output checks. IDs (`FUNC-001`, `FUNC-002`, …) are numbering only, never a meaning. Nothing in the skill names a feature kind, a UI kind or a file format |
| F15 | Time for many tests | (a) **Agent 2's time and turn limits grow with the number of FUNC tests** (a base plus an allowance per FUNC test, both in `.env`) · (b) one fixed limit | **(a)**: with no cap on tests, a fixed limit would cut a long plan off. The allowance is set after the first FUNC runs (start: 10 min and 40 turns per FUNC test) |
| F16 | One feature, several documented results | (a) **one test per feature, one `judged` claim per documented result statement + output checks** · (b) one test per statement | **(a)**: the steps run once; each documented statement about the result becomes its own claim, so the report shows exactly which part of the documentation holds |

---

## 4. Design

### 4.1 Agent 1 (test-design skill, generic)
- A **feature card** per documented feature in `summary` (cited): `name` (as the documents write it), `how_started` (the entry point or command the documents give), `context` (the documents' `use_context`, or `none`), `results` (each statement the documents make about the result), `testable` (true / false with the reason, F1).
- **One FUNC test per testable feature** (F1, F13, F16), as many as the documents give, numbered `FUNC-001`, `FUNC-002`, … with no meaning in the number (F14):
  - `preconditions`: `["LOAD-000"]` (plus another FUNC test only if the documents say this feature needs that one's result);
  - `steps`: intents ("open the context, start '<feature>' from '<entry point>', save any result into the output folder");
  - `observe`: Agent 2's description of what happened;
  - `expected`: one `judged` claim per documented result statement, in the documents' words; plus `output_created` / `output_valid` when the documents say a file is produced.
- **Open questions** for every feature that isn't testable (with the reason) and for every feature found only in `U1` (undocumented).
- **Self-check rules (generic, no count limit):** each FUNC test cites a document for its feature and each claim; names in claims are quoted from the sources; `context` is `none` or a context the host profile lists (otherwise no test, an open question); `output_*` checks only when a cited statement names a file result; FUNC tests never depend on UNIN; UNIN never depends on FUNC.
- **The skill's FUNC section names no test ID roles, feature kinds, UI kinds or file formats** (F14); `test_skills` checks it like the other skills.

### 4.2 Host profile (front matter only, data)
```yaml
contexts:
  - name: P&ID project            # matched by Agent 1 against the documents' use_context
    template: '%AppData%\...\DefaultProject'   # copied by code into sandbox/<name>/ (verify)
    open: the project file Project.xml          # how a user opens it (verify)
```
The exact values are verified on the machine (build step 1). No prose.

### 4.3 Code
- **Sandbox** (`execute/sandbox.py`, new): before Agent 2, copy each needed context template into `runs/<run>/sandbox/<context>/`, create `sandbox/output/`, pass both paths in Agent 2's input. A file-listing baseline of `output/` per FUNC test.
- **Output checks** (verdict engine): `output_created` (new files in `output/` since the test started), `output_valid` (JSON/XML parse, by extension); the files are attached as evidence; a capped excerpt goes to the judge.
- **Guardrail:** a `Type` text that is an absolute path must lie under the sandbox (FUNC tests only).
- **Report:** output files linked next to the screenshots.

### 4.4 Agent 2 (host-interaction skill, generic additions)
- Open the context from the sandbox the way a user would; create the needed document inside it.
- Act only on the feature the test names; handle its dialogs by the existing rules; in a save dialog use the given output folder.
- Screenshot each step; describe what happened in `notes`; never save anything else; kill the host after FUNC.

### 4.5 Judge (no change in its rule)
Input gets the output file's excerpt next to the screenshots. Same verdicts (PASS / PASS with a finding / FAIL / NEEDS_REVIEW), same guards.

---

## 5. Build steps

| # | Step | Done when |
|---|---|---|
| 1 | **Machine check** (manual): which template gives an empty project, how a user opens it, how a new document is created inside it, where the feature's save dialog points | `contexts` front matter filled for the host; screenshots of the manual path |
| 2 | Models: `Category.FUNC`, feature card, `output_created`, `output_valid` | strict-schema tests pass |
| 3 | Sandbox + output checks + guardrail | unit tests (copy, baseline, new-file detection, JSON/XML validity, path rule) |
| 4 | Self-check FUNC rules + `understanding.md` feature cards | unit tests per rule |
| 5 | Skills: test-design (feature cards, FUNC tests), host-interaction (FUNC principles) | `test_skills` incl. the no-product-names check |
| 6 | Judge: output excerpt in its input | unit test (request contents) |
| 7 | Report: output files | report test |
| 8 | Live run (elevated F5) | §6 |
| 9 | Docs | ARCHITECTURE.md D68+, ADR.md, this plan updated |

---

## 6. Verification

1. **Unit:** sandbox copy and baseline, new-file detection, JSON/XML validity, path guardrail, FUNC self-check rules, judge input. No API calls.
2. **Design only:** Agent 1 on the P&ID Exporter writes a feature card for every feature its documents describe (here: Export, with the results "the entire drawing to a JSON file" and "assets and lines, as well as all associated P&ID properties…"), one FUNC test per testable feature with one claim per documented result, a `context` from the host profile, and open questions for what it can't test (the Revit import) and for features seen only in `U1` (here e.g. "Export selection", "Language", "Info": undocumented).
3. **Live:** the Export test: the sandbox project is opened, a P&ID drawing created inside it, Export run, a JSON file in `sandbox/output/`; `output_created` and `output_valid` PASS (code), the content claim judged; the 14 existing tests unchanged; the host killed; UNIN PASS; nothing written outside the run folder except host churn.
4. **Failure paths:** no template → FUNC not written (open question); the feature's dialog asks for something lasting → not agreed, FAIL/NEEDS_REVIEW with screenshots; no file created → `output_created` FAIL; invalid JSON → `output_valid` FAIL.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Creating the needed document needs many UI steps | Generic principles + strong model (D67); screenshots per step; the judge sees the path; NEEDS_REVIEW over guessing |
| The feature writes outside the sandbox (fixed paths, temp files) | Output checks look only in `output/`; UNIN-000 reports leftovers; the guardrail stops typed paths outside |
| The feature asks for a licence or sign-in | Treated as "lasting" (D56): not agreed, the test ends with evidence |
| A real file content check needs domain knowledge | The judge compares with the documents' own words; strict content checks (schemas) are later, per app, as data |
| Host state between runs (recent projects, templates) | Kept as host churn; a clean host profile per run stays a later option (D65) |
| Long runs (no cap on tests) | Agent 2's time and turn limits grow per FUNC test (F15); the order puts features that only show something first, so a cut-off run still has the safe results |

---

## 8. Later
- FUNC for **standalone apps** (`host: none`): the app itself is the "host"; the same sandbox, act and output rules.
- A curated **test-data catalogue** for features that need real content (e.g. a P&ID with symbols and lines).
- Headless **host command channels** (e.g. an AutoCAD-family console) as host-profile data, to prepare contexts or double-check results without the UI.
- The deterministic **tools server** (deferred, see the tools discussion of 2026-10-14).
