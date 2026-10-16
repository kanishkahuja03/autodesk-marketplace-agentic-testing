# Plan: FUNC tests (does the app's documented feature work?), generic

> **Status:** v3, 2026-10-16: §3–§7 rewritten from the grill-me decisions in §8 (2026-10-15/16). v2 was the draft for the review (no cap on FUNC tests, no fixed test shapes). Builds on [`ARCHITECTURE.md`](ARCHITECTURE.md) (D1–D67), [`LOAD_TESTS_PLAN.md`](LOAD_TESTS_PLAN.md) (LOAD, L1–L29) and [`ADR.md`](ADR.md). Once built, the decisions in §3 become ARCHITECTURE.md D68+ and ADR entries.
> **Rule kept from D1/D67:** nothing in the code or the skills names a product. App knowledge comes from the app's documents and files (D*, I*, U1, F1); host knowledge only from the host profile's **front matter** (data). The example below (the P&ID Connector Exporter) is only an example.

---

## 1. Goal

Today a run tests **ENV → INST → LOAD → UNIN** (14 PASS with generic skills, runs 20261014-175347 and -194215). FUNC adds one category between LOAD and UNIN: **run a feature the documents describe, the way a user would, and check its result.**

```
ENV → INST → LOAD (entry point present) → FUNC (prepare context → run feature → check result) → kill host → UNIN
```

| FUNC checks (generic) | Example for the P&ID Connector Exporter (derived, not hard-coded) |
|---|---|
| The context the documents require can be set up without touching the user's data | D2: "the user must be in a P&ID project and have a drawing open" → a P&ID drawing inside a **copy** of a sample project, in the run folder (`context/<name>/`) |
| The documented feature can be started from its entry point | D2: "The 'Export' button is used to export the entire drawing to a JSON file" → Tools → "Export P&ID" |
| It produces the documented result | a JSON file, saved into the test's output folder (`evidence/<test_id>/`) |
| The result matches what the documents say about it | D2: "assets and lines, as well as all associated P&ID properties…" → the judge compares the file's content with the claim |

**Demo acceptance:** one F5 run on the P&ID Exporter gives a FUNC result with evidence (screenshots of each step, the output file), the host is killed, and UNIN still runs and passes. The other 14 tests are unchanged.

**Out of scope (later):** features that need another product or service (here: the Revit Importer), network or account actions, features that change the host's settings, standalone apps (`host: none`, see §9), EXE installers.

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

FUNC adds **four** generic things: a context copied into the run folder (F2), one action policy by lasting effect (F4), an output folder per test (F5), and an output check (F7).

---

## 3. Decisions (v3)

Each row is decided; the last column points to the decision log in §8. The F-numbers are kept from v2 so earlier notes still match.

| # | Topic | Decision | §8 |
|---|---|---|---|
| F1 | Which features become tests | **Every documented feature whose result the documents describe**, no limit. A feature is testable only if (1) the documents describe its result, (2) using it as documented needs only class 0–2 actions (F4), (3) the context it needs is available (F2), (4) it needs nothing outside this machine (another product, a network, an account). Agent 1 judges each point; if one fails → an **open question naming that point**, no test. Features seen only in `U1` → an open question ("undocumented feature"), no test. Features that change the host's lasting settings are class 3, so **never tested** | F1 (confirmed 2026-10-15), Q9 |
| F2 | Where the feature's context comes from | One of three, all **inside the run folder**: **none**; a **host-profile context** (F3); or a **sample** from the samples folder (F18). Templates and samples are **copied by code into `runs/<run>/context/<name>/`**; the original is never opened. **The LLM never creates content**: when the claims need content and no sample fits, there is no test for them (open question). Never the user's own files | Q1, Q6-C, Q7, Q7a |
| F3 | How the host profile describes contexts | Front matter `contexts:`, each with a `name` and **either** `template:` (a folder code copies) **or** `create:` (the host creates it through its own UI at a location code gives). Which one is decided per context by the machine check (§5 step 1). **No** launch argument, `open:` or restart data: contexts are opened only through the host's UI. Code and skills don't change between `template:` and `create:` | Q1, Q2 |
| F4 | What Agent 2 may do (all tests) | **One policy by lasting effect**, judged by Agent 2: **class 0 View** (nothing remains): always. **Class 1 Session** (once the host is killed without saving, nothing remains outside the run folder; e.g. panels opened or moved, unsaved documents, new files inside the run folder): when the test needs it. **Class 2 Reversible**: only when the test needs it, undone right after that test, recorded in `notes` before and after. **Class 3 Lasting** (save over existing files, sign-in, licence, update, "Always…", delete): never. **Unclear = class 3.** **Only FUNC may run a feature of the app**; LOAD may use classes 0–2 to show its entry point, never run anything. FUNC may also prepare its context (open or create it, new documents inside it) and answer the feature's own dialogs. In FUNC the app's file dialogs may be used for paths inside the run folder. Replaces the D62 ("reveal, never act") and D65 ("view-only changes") wording | Q6-A, Q2 |
| F5 | Where outputs go | **Hard rule, every test:** anything the **app under test** produces when a test runs one of its features is saved into **`evidence/<test_id>/`** (installer and tool logs keep today's paths, e.g. `evidence/install.log`; user, 2026-10-16) (path given in Agent 2's input). No logic for any particular kind of window. **No path guardrail** for now: the skill rule plus the code check (F7) enforce it; add a guardrail only if runs show files landing outside the run folder | Q3 |
| F6 | Who decides the result | **Code** decides only whether the test produced a file (`output_created`). **The judge** decides everything about the content and the UI (`judged` claims) from the screenshots and a capped excerpt of each output file | Q4 |
| F7 | Checks | **`output_created`** (new) + **`judged`** (exists). `output_created` is decided from the evidence, never from Agent 2's value (added to `UI_CHECKS`): `key: output_files`, `check: output_created`, `value: null`; PASS = at least one non-empty file in `evidence/<test_id>/`. **No `output_valid` and no list of file formats in code.** Strict validation later only as data (a schema from the host profile or the app's documents) | Q4, Q11.2 |
| F8 | Preconditions | **`LOAD-000` only**, plus another FUNC test only when a cited statement says this feature needs that one's result. A NEEDS_REVIEW or FAIL in the entry-point LOAD tests doesn't block FUNC. No new rule in the verdict engine | Q10 |
| F9 | Host session | **One host session for all FUNC tests**, after LOAD. **Tidy up between tests**: close what the previous test opened, never saving, back to the state the host was in before that test, and note what was closed. **At most one restart per test**, only when something goes wrong (crash, hang, a state that can't be tidied back), with the same exact args; Screenshot first. A second problem in the same test → record it as executed with what was seen, go on to the next test. Bringing the host up at the start of a test when it isn't running is a **normal start**, not a restart. Applies to **every test that uses the host** (LOAD and FUNC). **LLM only**: stated strictly in the skill, no code counting | Q8, Q8a |
| F10 | Time limit | **Replaced by F15** | Q11.4 |
| F11 | Cleanup and host state | Everything a run creates stays in the run folder (`context/`, `evidence/`) and is kept as evidence; code deletes nothing. **No backup, restore or detection of the host's user state for now** (recent files, layout, project lists). **To review after the first FUNC runs** | Q3, Q6-B |
| F12 | Language of the app | Generic: the claim keeps the documents' words; Agent 2 and the judge read whatever language the app shows (run 20261014-194215: a German UI, no hints) | unchanged |
| F13 | Order of the FUNC tests | Tests that need only class 0–1 actions first, then those that also need class 2; within a class, the documents' order. No cap on the number (time grows by F15) | Q9 |
| F14 | Test shapes | Generic rules for every FUNC test: a cited feature, the context it needs, one claim per documented result in the documents' words, and `output_created` when a cited statement names a file result. IDs (`FUNC-001`, …) are numbering only. Nothing in the skills names a feature kind, a UI kind or a file format | unchanged |
| F15 | Time and turns for many tests | Agent 2's time and turn limits = a base (today's `AGENT2_TIMEOUT_MIN`, `AGENT2_MAX_TURNS`) **plus an allowance per FUNC test**, both in `.env` (`AGENT2_FUNC_MIN_PER_TEST`, `AGENT2_FUNC_TURNS_PER_TEST`; start: 10 min and 40 turns; set after the first FUNC runs) | F15 (confirmed 2026-10-15) |
| F16 | One feature, several documented results | One test per feature; **one `judged` claim per documented result statement**, plus `output_created` when a file is named. The steps run once | F16 (confirmed 2026-10-15) |
| F17 | Judge input (screenshots: all judged tests; the rest: FUNC) | **Screenshots, for every judged test (LOAD too; user, 2026-10-16):** the ones Agent 2 names in `record_observation`'s `evidence` first, then the latest, up to `JUDGE_MAX_IMAGES` in `.env` (start: 6), shown in the order taken. So that Agent 2 can name them, each screenshot's tool result tells it the saved file name. Built in §5 step 2, so the LOAD rerun gate covers it. **Quotes:** the test's `source` plus the feature card's citations (not the entry point's). **Output files:** an excerpt of each, the start of the file, within one total cap `JUDGE_FILE_EXCERPT_CHARS` (start: 15,000), with a note when it was cut off and the full size; a file that doesn't decode as text → "binary file, <size>, not shown". Same verdicts and guards as today | Q5, Q11.2, Q11.3 |
| F18 | Samples folder (temporary, POC) | **One setting `SAMPLES_DIR` in `.env`**, kept by the user; never a path in code or a skill. Code **lists** it at design time (names, file types, sizes; never opens or interprets them); Agent 1 decides which sample fits a feature's context and cites its choice; code copies it (F2). For hosts whose documents live inside a project, the whole project folder goes there. Unset or no fitting sample → open question, no test. **To automate after the POC** | Q7, Q7a |

---

## 4. Design

### 4.1 Agent 1 (test-design skill, generic)
- **Inputs** (in addition to today's evidence pack): the host profile's `contexts:` names, and the **listing of `SAMPLES_DIR`** (names, file types, sizes) made by code.
- **Feature cards** in `summary.features` (cited), one per documented feature: `name` (as the documents write it), `how_started` (the entry point or command the documents give), `context` (the documents' `use_context`, or `none`), `sample` (the chosen sample's name, or `none`), `results` (each statement the documents make about the result), `action_class` (the highest action class it needs, 0–2; `class` is a Python keyword), `testable` + `reason` (F1, naming the point that fails). `entry_point` stays as it is, for LOAD.
- **One FUNC test per testable feature** (F1, F13, F16), numbered `FUNC-001`, `FUNC-002`, … in the order of F13:
  - `preconditions`: `["LOAD-000"]`, plus another FUNC test only by citation (F8);
  - `steps`: intents ("open the given context, start '<feature>' from '<entry point>', save any result into the test's output folder");
  - `observe`: Agent 2's description of what happened, plus `output_files` when a file result is documented;
  - `expected`: one `judged` claim per documented result statement, in the documents' words; plus `output_created` when a cited statement names a file result.
- **Open questions:** every feature that isn't testable (with the point that fails), every feature found only in `U1`, and every content claim without a fitting sample ("needs a sample: <what the documents say must be open>").
- **Self-check rules (generic, no count limit):** each FUNC test and each claim cites a document; names in claims are quoted from the sources; `context` is `none` or a name from the host profile's `contexts:`; `sample` is `none` or a name from the samples listing; `output_created` only when a cited statement names a file result; tests are in class order (F13); preconditions are `LOAD-000` and FUNC tests only; FUNC never depends on UNIN and UNIN never on FUNC.
- **The skill's FUNC section names no test ID roles, feature kinds, UI kinds or file formats** (F14); `test_skills` checks it like the other skills.
- `understanding.md` lists every feature card, untestable ones with their reason.

### 4.2 Host profile (front matter only, data)
```yaml
contexts:                     # optional; only what the machine check (§5 step 1) shows is needed
  - name: <context name>      # matched by Agent 1 against the documents' use_context
    template: <folder>        # either: a folder code copies into context/<name>/
  # or
  - name: <context name>
    create: true              # or: the host creates it through its own UI at the location code gives
```
No launch arguments, no `open:` field, no restart flag, no prose. The values are verified on the machine (§5 step 1).

### 4.3 Code
- **Config** (`config.py`, `.env.example`): `SAMPLES_DIR`, `JUDGE_MAX_IMAGES`, `JUDGE_FILE_EXCERPT_CHARS`, and the per-FUNC-test time and turn allowances (F15).
- **Design side** (`design/samples.py`, new): list `SAMPLES_DIR` for Agent 1 (names, types, sizes; nothing opened); the FUNC self-check rules (§4.1); feature cards in `understanding.md`. Nothing here imports from `execute/`.
- **Execution side** (`execute/context.py`, new): before Agent 2 starts, copy each needed template or sample into `runs/<run>/context/<name>/`, and record a listing (names, sizes, times) of each **original** sample; after the run, compare it again, so a changed original is reported. Create an empty `evidence/<test_id>/` for each FUNC test (the recorder never writes there, so every file in it came from the test).
- **Agent 2's input:** per FUNC test, the context path (the copy, or the location for `create:`) and its output folder. Time and turn limits scaled by F15.
- **Verdict engine:** `output_created` decided from the contents of `evidence/<test_id>/` (F7); all new files attached as evidence.
- **Judge** (`judge.py`): screenshot choice, quotes and file excerpts as in F17.
- **Report:** output files linked next to the screenshots; a changed original sample shown as a finding.
- **No new guardrail** (F5); the `App` guardrail stays as it is (F3).

### 4.4 Agent 2 (skills, generic)
- **host-interaction.md:** the action policy (F4) replaces "reveal, never act" and "view-only changes", for LOAD and FUNC; the restart rule (F9) replaces today's start-crash rule; a FUNC section: open the given context through the host's UI as a user would, run only the feature the test names, answer its own dialogs by the existing dialog rules, save results only into the test's output folder, tidy up between tests, kill the host after the last test.
- **evidence.md:** the hard rule "everything a test produces goes into `evidence/<test_id>/`" (F5); for FUNC, name in `evidence` the screenshots that show each result (F17).

### 4.5 Judge (judge.md)
Same verdicts (PASS / PASS with a finding / FAIL / NEEDS_REVIEW) and guards. Its input gains the output files' excerpts. One addition in the spirit of "hidden is not missing": a claim about a part of a file that the excerpt doesn't show (cut off) is NEEDS_REVIEW, never FAIL.

---

## 5. Build steps

The LOAD skill change comes **first** and is checked by a LOAD-only rerun before any FUNC code builds on it (Q12): there is little room to revert later.

| # | Step | Done when |
|---|---|---|
| 1 | **Machine check** (manual): the user puts the sample (for a project-based host, the whole project folder) into `SAMPLES_DIR`; check that a **copy** of it in a run folder opens through the host's UI with all its paths inside the copy; decide whether any host-profile `contexts:` entry is needed for the demo and, if so, `template:` or `create:` | `SAMPLES_DIR` set; result of the copy check noted (screenshots of the manual path); `contexts:` filled only if needed |
| 2 | **Skills, action policy:** host-interaction.md (F4, F9) and evidence.md (naming screenshots) for all tests; the F5 output rule goes in with step 7, when Agent 2's input gives the output folders; **judge screenshot choice** (F17: saved names in the screenshot results, Agent 2's picks first, `JUDGE_MAX_IMAGES`) | `test_skills` passes, incl. the no-product-names check; unit tests for the screenshot choice; all tests pass |
| 3 | **Gate: LOAD-only rerun** (Q12 step 2) | The same 14 PASS and the same findings as run 20261014-194215; otherwise revert the wording to commit 7ea25d7 and rethink before going on |
| 4 | Models: `Category.FUNC`, `FeatureCard`, `Summary.features`, `Check.OUTPUT_CREATED` (in `UI_CHECKS`), host-profile `contexts` | strict-schema tests pass |
| 5 | Config: the new `.env` keys (§4.3) | config tests pass; `.env.example` updated |
| 6 | Design side: samples listing for Agent 1, FUNC self-check rules, feature cards in `understanding.md`, test-design skill FUNC section | unit tests per rule; `test_skills` |
| 7 | Execution side: context copies + original-sample listing, empty output folders, Agent 2's input, F15 limits, host-interaction FUNC section, evidence.md output rule (F5) | unit tests (copy, listing compare, folders, input text, limits) |
| 8 | Verdict + judge: `output_created`, screenshot choice, quotes, file excerpts, judge.md addition | unit tests (check results, request contents) |
| 9 | Report: output files, changed-original finding | report test |
| 10 | Design-only and live runs | §6 steps 3–5 |
| 11 | Docs | ARCHITECTURE.md D68+, ADR.md, this plan updated |

---

## 6. Verification

Each step gates the next. Steps 1–5 are the demo acceptance.

| # | Step | Passes when | API |
|---|---|---|---|
| 1 | **Unit tests** | Sample copy into `context/<name>/`; `SAMPLES_DIR` listing; original-sample compare; `output_created` (a file → PASS, empty folder or empty file → FAIL); excerpt cap, cut-off note and binary case; judge screenshot choice (Agent 2's picks first, then the latest, up to the cap) and quotes; FUNC self-check rules (citations, known `context`/`sample`, class order, preconditions); `test_skills` with no product names | No |
| 2 | **LOAD-only rerun** after the skill change | Same 14 PASS and findings as 20261014-194215 | ~8 min |
| 3 | **Design only, `SAMPLES_DIR` set** (P&ID Exporter) | A feature card for every documented feature; Export testable with the sample, one claim per documented result statement ("the entire drawing to a JSON file", "assets and lines, as well as all associated P&ID properties…") and `output_created`; the Revit import an open question (point 4 of F1); features seen only in `U1` open questions | Agent 1 |
| 4 | **Design only, `SAMPLES_DIR` unset** | No FUNC test for the content claims; an open question naming the missing sample | Agent 1 |
| 5 | **Full live run** | The copy of the sample opened, Export run, a file in `evidence/FUNC-001/`; `output_created` PASS; content claims judged from the excerpt and screenshots; the 14 existing tests unchanged; the host killed; UNIN PASS; the original sample unchanged (listing compare) | Yes |
| 6 | **Genericity check, second app** (design only) | Sensible feature cards or open questions for another app, with no code or skill change. **Later** | Agent 1 |

**Failure paths** (unit tests or observed in runs): no fitting sample → no FUNC test, open question; the feature asks for something lasting → not agreed, FAIL or NEEDS_REVIEW with screenshots; the file saved elsewhere or not at all → `output_created` FAIL with screenshots; a crash → one restart, then the next test; a claim about a cut-off part of the file → NEEDS_REVIEW.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| A copied sample isn't relocatable (its paths point back to the original) | Checked by hand before building (§5 step 1); the original-sample listing compare reports a changed original in every run |
| The LOAD wording change makes today's 14 PASS worse | Built first and gated by a LOAD-only rerun (§5 step 3); revert to commit 7ea25d7 |
| Agent 2 misjudges an action's class | Unclear = class 3; every class 2 change noted before and after; the judge sees the screenshots; the safety net (F11) is reviewed after the first runs |
| The host keeps user state between runs (layout, recent files, project lists) | Accepted for now (F11); review after the first FUNC runs, then a host-profile `user_state:` list with code backup and restore |
| The feature saves outside the run folder (default folders, fixed paths) | `output_created` looks only in `evidence/<test_id>/` → FAIL with screenshots, never a silent PASS; add a path guardrail if it happens (F5) |
| The feature asks for a licence or sign-in | Class 3: not agreed, the test ends with evidence |
| A content check needs domain knowledge, or the file is larger than the excerpt | The judge compares with the documents' own words; cut-off parts → NEEDS_REVIEW; strict schemas later, as data |
| Restart loops or long runs | At most one restart per test (skill rule); time and turns grow per FUNC test (F15); class order puts the safest tests first, so a cut-off run still has their results; add code counting only if the rule is broken in runs |
| `SAMPLES_DIR` is a POC shortcut | A setting only, never in code or skills; automate after the POC (F18) |

---

## 8. Decision log (grill-me, 2026-10-15/16)

The decisions as agreed during the review; §3 is the summary that the design follows.

| Q | Decision |
|---|---|
| Q1 (F2/F3) | A context in the host profile's front matter declares **either** `template:` (a folder code copies) **or** `create:` (the host creates it through its own UI at a location code gives). Build step 1 decides which, per context, by checking that a copy opens with all its paths inside the run folder. Code and skills don't change between the two; only the data does |
| Q2 (F3/F9) | Contexts are opened **only through the host's UI**, the way a user would. No launch argument per context and no `open:` or restart flag in the host profile. The `App` guardrail stays as it is (exact host `args`); a restart, if Agent 2 judges one is needed, uses the same args. In FUNC tests Agent 2 may use the app's own file dialogs, but only for paths inside the run folder |
| Q3 (F5, F11) | **Hard rule, for every test:** anything a test produces is saved into the existing evidence folder, under **`evidence/<test_id>/`** (path given in Agent 2's input). There is no separate sandbox output and no logic for any particular kind of window (e.g. a save dialog); Agent 2 works out how to save there in whatever app it drives. Features that save nothing are handled like today's `judged` tests (screenshots and Snapshots in `evidence/`). Copied context templates are input, not evidence: they go to `runs/<run>/context/<name>/`. Nothing is written outside the run folder |
| Q3 (enforcement) | **No new guardrail for paths.** The rule is enforced by the skill (evidence.md) plus the code check (a documented file result that is missing from `evidence/<test_id>/` → FAIL with the screenshots). If runs show files landing outside the run folder, add a path guardrail then |
| Q4 (F6/F7) | **Code checks only `output_created`**: a new, non-empty file in `evidence/<test_id>/` that the recorder didn't write itself. **No `output_valid` and no list of file formats in code.** The judge decides everything about the file's content (structure and the documented claims) from a capped excerpt, given only when the file decodes as text (no format list), next to the screenshots. Later, if an app needs strict validation, its schema comes as data (host profile or the app's documents), never from code |
| Q5 (judge input) | Agent 2 names the screenshots that show each result in `record_observation`'s `evidence`. The judge sees those first, then the latest ones, up to a cap set in `.env` (start: 6). The judge still decides and must cite a screenshot it was shown. For FUNC claims the judge's quotes come from the test's `source` plus the feature card's citations, not the entry point's |
| Q6-A (action policy, F4) | **One policy for every test, by lasting effect**, judged by Agent 2 (LLM), written once in the skill: **class 0 View** (nothing remains: menus, hover, scroll, zoom, maximize, tabs): always allowed. **Class 1 Session** (remains only until the host is killed, which code always does without saving: open, move or dock panels and palettes, unsaved documents, commands on a document of the run): allowed when the test needs it. **Class 2 Reversible** (a lasting change Agent 2 can undo): only when the test needs it, undone right after that test, recorded in `notes` before and after. **Class 3 Lasting** (save over existing files, sign-in, licence, update, "Always…", delete): never. Unclear counts as class 3. **Only FUNC may run a feature of the app**; LOAD may use classes 0–2 to show its entry point (e.g. open a panel), but never run anything. FUNC may also prepare the context the test names (open or create it, new documents inside it, inside the run folder) and answer the feature's own dialogs. Replaces the "reveal, never act" (D62) and "view-only changes" (D65) wording |
| Q6-B (safety net) | **No code safety net for now** (no backup, restore or detection of the host's user state). The current case is expected to pass without it. **To review after the first FUNC runs:** if the host's state is found changed between runs, add a host-profile `user_state:` list (registry keys, folders), with code backing up and restoring the registry and detecting folder changes |
| Q6-C (content) | **The LLM never creates content.** When the claims need a context with content (more than an empty template), Agent 1 says so, with the reason, and **asks the user to supply a sample** (e.g. a sample project). Code copies the supplied sample into `runs/<run>/context/<name>/`; the original is never opened. Without a sample, those claims are not tested (open question, no FUNC test for them). How the user supplies it: see Q7 |
| Q6-D (LOAD impact) | The policy from Q6-A applies to LOAD as well. After the skill change, rerun the LOAD-only plan before any FUNC run and compare it with run 20261014-194215 (14 PASS). If LOAD gets worse, revert the LOAD skill wording to today's (commit 7ea25d7) |
| Q7 (supplying the sample) | **Temporary, for the POC: no user involvement.** One fixed samples folder kept by the user (for now one sample for the current host). When a feature's claims need content, the sample is searched in that folder. Details in Q7a. **To automate after the POC** (e.g. samples per input, asked at the review gate) |
| Q7a (samples folder) | The fixed folder is **one setting in `.env`** (`SAMPLES_DIR`), never a path in code or a skill. At design time code **lists** it (names, file types, sizes; never opens or interprets the files) and gives the listing to Agent 1. Agent 1 decides whether a feature needs content and which sample fits the documents' `use_context`, and cites its choice in the test. Code copies the chosen sample into `runs/<run>/context/<name>/` before Agent 2 starts; Agent 2 opens the copy through the host's UI. For hosts whose documents live inside a project, the whole project folder goes into `SAMPLES_DIR`. `SAMPLES_DIR` unset or no fitting sample → no FUNC test for those claims (open question) |
| Q8 (session, F9/F13) | **One host session for all FUNC tests, tidied between tests, with at most one restart per test.** (1) Agent 2 starts the host once (after LOAD it is already running) and runs the FUNC tests in order. (2) **Between tests**, Agent 2 tidies up: it closes what the previous test opened, never saving (class 1), until the host is back at its start state, and writes what it closed in `notes`. No restart is needed for this. (3) **Restart only when something goes wrong** (crash, hang, a state Agent 2 can't tidy back): Screenshot first, then kill the host and start it again with the same exact args (Q2). **Each test may use at most one restart**, but doesn't have to; the allowance belongs to that test and isn't carried over or shared. (4) If the same test needs a second restart, Agent 2 records it as executed with what it saw (the judge decides from the evidence) and moves on to the next test, which again has its own one restart. (5) After the last FUNC test: kill the host, then UNIN, as today |
| Q8a (start vs restart) | Bringing the host up at the start of a test when it isn't running is a **normal start**, always allowed, and doesn't use that test's restart. A **restart** is only killing and starting again within a test because of a problem. The rule applies to **every test that uses the host** (LOAD and FUNC), so the skill has one rule. **Handled by the LLM only:** the skill states strictly "at most one restart per test"; no code counting or guardrail |
| Q9 (testable, order; F1/F13) | A feature is **testable** only if (1) the documents describe its result, (2) using it as documented needs only class 0–2 actions (Q6-A), (3) the context it needs is available (none, a host-profile template, or a sample from `SAMPLES_DIR`), and (4) it needs nothing outside this machine (another product, network, account). Agent 1 judges each point from the documents; if one fails → an open question naming that point, no test. **Order:** tests that need only class 0–1 actions first, then those that also need class 2; the same class keeps the documents' order. Replaces F1's list of example reasons |
| Q10 (preconditions, F8) | A FUNC test's preconditions are **`LOAD-000` only**, plus another FUNC test only when a cited statement says this feature needs that one's result. A NEEDS_REVIEW or FAIL in the entry-point LOAD tests doesn't block FUNC: each FUNC test is judged on its own evidence, and a really missing entry point shows up in both. No new rule in the verdict engine |
| Q11.1 (feature cards) | `Summary.features: list[FeatureCard]` with `name`, `how_started`, `context` (the documents' words or `none`), `sample` (chosen sample name or `none`), `results` (cited statements), `class` (0–2), `testable` + `reason`. `entry_point` stays as it is for LOAD; `understanding.md` lists every feature, untestable ones with their reason |
| Q11.2 (`output_created`) | A check decided from the evidence (added to `UI_CHECKS`, like `window_in_ui`): `key: output_files`, `check: output_created`, `value: null`. Agent 2 reports the file names for the notes only; code decides from the contents of `evidence/<test_id>/`. Several new files → all attached, an excerpt of each to the judge within one total cap |
| Q11.3 (excerpt cap) | `JUDGE_FILE_EXCERPT_CHARS` in `.env` (start: 15,000). The start of the file, with a note that it was cut off and the full size; a file that doesn't decode as text → "binary file, <size>, not shown" |
| Q11.4 (plan fixes) | When §3–§5 are rewritten: F10 is replaced by F15; the `profile_ignore` in F11 is removed (it doesn't exist; see Q6-B); `sandbox/output/` → `evidence/<test_id>/` and `sandbox/<context>/` → `context/<name>/` |
| Q12 (verification, §6) | Steps, each gating the next: (1) unit tests, no API; (2) LOAD-only rerun after the skill change, same 14 PASS and findings as 20261014-194215; (3) design only on the P&ID Exporter with `SAMPLES_DIR` set; (4) design only with `SAMPLES_DIR` unset; (5) full live run, including a check that the original sample is untouched (listing before and after). Steps 1–5 are the demo acceptance. (6) The genericity check on a second app (design only) **comes later**. Because there is little room to revert, the LOAD skill change (Q6-A) is built and checked with step 2 **first**, before any FUNC code is built on top of it |

---

## 9. Later
- FUNC for **standalone apps** (`host: none`): the app itself is the "host"; the same context, action-policy and output rules (F2, F4, F5).
- A curated **test-data catalogue** for features that need real content (e.g. a P&ID with symbols and lines), replacing the temporary `SAMPLES_DIR` (F18): samples per input, asked at the review gate.
- A **host-state safety net** (F11, Q6-B), if the first FUNC runs show the host's user state changing between runs: a host-profile `user_state:` list, with code backing up and restoring it.
- A **path guardrail** (F5), if runs show files landing outside the run folder.
- Headless **host command channels** (e.g. an AutoCAD-family console) as host-profile data, to prepare contexts or double-check results without the UI.
- **Undocumented (U1-only) features:** let Agent 1 decide from the app's own text whether a light "it opens without errors" test is worth writing (user, 2026-10-15: LLM logic should decide this after the POC).
- The deterministic **tools server** (deferred, see the tools discussion of 2026-10-14).
