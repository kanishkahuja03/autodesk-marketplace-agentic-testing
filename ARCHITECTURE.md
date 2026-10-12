# Architecture V2: Generic Plug-in / App Validation Agents

> **Status:** v2.0, 2026-10-12. This is the build plan for the product.
> **Supersedes:** [`ARCHITECTURE.md`](ARCHITECTURE.md) v0.3. Where they disagree, **this document wins**, including over what is already in `CodeBase/`.
> **Inputs to this version:** [`ARCHITECTURE_COMPARISON.md`](ARCHITECTURE_COMPARISON.md) (ours vs `AppStore automation/`), [`AGENT_TOOLING_REVIEW.md`](AGENT_TOOLING_REVIEW.md) (tool lists, one by one), [`DESKTOP_UI_AUTOMATION_RESEARCH.md`](DESKTOP_UI_AUTOMATION_RESEARCH.md).

---

## 1. Context

Store QA for desktop plug-ins and apps is manual: install, check it registered, check it loads, check it uninstalls cleanly. That's slow and varies between reviewers.

We build a **generic** two-agent pipeline that takes an app's **documentation and installer** and returns a **report with code-decided verdicts and evidence**:
- **Agent 1** designs the tests.
- **Agent 2** runs them on a real Windows machine through a ready-made MCP server.

The goal **now** is a **demo POC with minimal development effort**, built from ready-made parts (OpenAI Agents SDK, Windows-MCP, existing libraries). Cost is not a concern.

**Generic means:** nothing in the core is tied to Autodesk or any other vendor. Product-specific knowledge lives in **host notes** (Markdown skill files). AutoCAD Plant 3D 2027 is just the first host, and the **P&ID Connector Exporter** is the demo app.

---

## 2. Decisions (final)

| # | Topic | Decision |
|---|---|---|
| D1 | Scope | Generic: any Windows desktop plug-in or standalone app. Host specifics only in host notes. |
| D2 | LLM | **Enterprise OpenAI API** (platform.openai.com). Model name set in `.env`. Gemini removed. |
| D3 | Agent framework | **OpenAI Agents SDK** (`openai-agents`, Python) |
| D4 | Agent 1 | **Blind, single pass.** No tools, no machine access. Output: `understanding.md` + `testcases.yaml`. |
| D5 | Agent 2 | **One agent session for the whole plan**, driving the machine **only through Windows-MCP**. No action catalogue of our own. |
| D6 | UI interaction | **[Windows-MCP](https://github.com/CursorTouch/Windows-MCP)** (reads the accessibility tree, then clicks, types and takes screenshots) |
| D7 | Verdict | **Code** compares observed values with expected ones. The LLM never sets PASS/FAIL. |
| D8 | Demo test levels | **ENV, INST, UNIN** (LOAD and FUNC later) |
| D9 | Human review gate | **None.** Fully automatic. |
| D10 | Doc extraction | **Keep the existing `intake.py`** (pypdf, python-docx, bs4) |
| D11 | Tracing | **Local JSONL only.** OpenAI tracing disabled. |
| D12 | Machine | Dev machine, **run as administrator**. Risk accepted. VM later. |
| D13 | "Skills" | **SKILL.md-style Markdown files** loaded into each agent's instructions. OpenAI's hosted Skills API is not used (it runs in OpenAI's cloud). |
| D14 | Demo app | P&ID Connector Exporter (Kleen Software) on Plant 3D 2027 |
| D15 | Host lookup | **Done by Agent 1** (LLM reasoning over documents + installer facts), not by keyword code. Agent 1 picks a `host_id` from the available host notes, or `none` / `unknown`, and cites why. |

**Defaults taken for the open review points** (§C of the tooling review; change there if the team disagrees):
- PowerShell is allowed, with strict rules.
- Registry and FileSystem are **read only by instruction**, plus a guardrail.
- Uninstall uses `msiexec /x` first, then the Control Panel UI if UAC allows.
- Agent 2 resolves placeholders during ENV.

---

## 3. High-level flow

```
 inputs/<app>/                        DESIGN SIDE (no machine access)
 ├─ *.txt/.pdf/.docx/.html  ──►  [S0 Intake]  ──►  [S1 Installer static read]
 └─ installer (.msi/.exe/.zip)        (code)            (code)
                                                                │
                                                                ▼
                                      ┌──── AGENT 1: Test Designer (OpenAI, no tools) ────┐
                                      │ skills: test-design + all hosts/*.md (catalogue)  │
                                      │ decides host_id, then designs the tests           │
                                      │ output_type = TestPlan  →  self-check → retry ≤2  │
                                      └───────────────────────────────────────────────────┘
                                                                │ testcases.yaml, understanding.md
                                      EXECUTION SIDE            ▼
                                      ┌──── AGENT 2: Test Executor (OpenAI + Windows-MCP) ──┐
                                      │ skills: windows-installer + evidence + hosts/<id>   │
                                      │ one session: ENV → INST → UNIN                      │
                                      │ output_type = RunObservations (no status)           │
                                      └───────────────┬─────────────────────────────────────┘
                                                      │  MCP stdio (13 allowed tools)
                                                      ▼
                                           Windows-MCP  ──►  Windows + host app + plug-in
                                                      │
                                      [Verdict engine (code)] → [Report] → runs/<app>/<ts>/
```

---

## 4. Design side

### S0. Intake (existing code: keep)
`design/intake.py`, unchanged. It sorts files by type, extracts text with numbered lines (D1, D2…), hashes every file, reads the claimed signer, and writes `intake_manifest.json` + `documents/`.

### S1. Installer static read (existing code: keep)
`design/static_read.py` and `design/msi.py`, unchanged. They read the MSI without running it and write `installer_facts.json`: properties, files, install roots, custom actions, registry entries, embedded docs, and bundle manifest if present.
- The `BundleManifest` model is a **host-specific reader** (Autodesk `PackageContents.xml`). It stays as an optional reader. The core must not depend on it.
- EXE and ZIP readers come later.

### Host lookup (done by Agent 1, no separate code step)
Keywords can't always identify the host from a description, so **Agent 1 decides it** as part of its single pass:
- Code loads every `skills/hosts/*.md` file and gives Agent 1 the catalogue: the `host_id` and the content of each file.
- Agent 1 reasons over the documents **and** the installer facts (e.g. `PackageContents.xml` says `Platform="Plant3D"`), then sets:
  - `app.host_id` to a catalogue entry;
  - `none` for a standalone Windows app;
  - `unknown` if it can't tell, with an open question saying why.
- It also sets `app.host_evidence`, with source quotes that are checked like every other citation.
- The chosen `host_id` is recorded in `testcases.yaml`. Agent 2 loads `skills/hosts/<host_id>.md` from there. For `unknown`, it loads only the generic skills.
- Later, when there are many host notes: replace the full catalogue with a short index plus a local read-only tool that loads one note on request (a knowledge file, not machine access).

### Agent 1: Test Designer (new)

| Item | Spec |
|---|---|
| Agent | `agents.Agent(name="test-designer", instructions=<skills>, output_type=TestPlan, model=$OPENAI_MODEL)` |
| Tools | **None** |
| Input message | All extracted document text (with doc IDs and line numbers), `installer_facts.json` |
| Instructions | `skills/test-design/SKILL.md` + the host notes catalogue (all `skills/hosts/*.md`) |
| Output | `TestPlan` (§6.1). Code writes `testcases.yaml` (+ `.json`) and renders `understanding.md` from it. |
| Self-check (code) | (1) schema valid; (2) every `source.quote` really appears in the cited document text; (3) every `${PLACEHOLDER}` used is listed in `required_env`; (4) ENV, INST and UNIN each have ≥1 test; (5) every `expected.check` is a supported type; (6) `host_id` is a catalogue entry, `none` or `unknown`, and `host_evidence` quotes are real. On failure, the error list is sent back and the agent retries, at most 2 times. |
| Rules | Test the plug-in, not the host's API. Never guess (`null` + an open question). Machine values are always placeholders. Every test cites its source. |

---

## 5. Execution side

### Agent 2: Test Executor (new)

| Item | Spec |
|---|---|
| Agent | `agents.Agent(name="test-executor", instructions=<skills>, mcp_servers=[windows_mcp], output_type=RunObservations, model=$OPENAI_MODEL)` |
| MCP server | `MCPServerStdio(command="uvx", args=["windows-mcp==<pinned>", "serve", "--tools", "<allow-list>"])`, plus `tool_filter=create_static_tool_filter(allowed_tool_names=[…])`. It runs in its own Python 3.13 environment managed by uvx. |
| Input message | The whole `testcases.yaml`, the run folder path (where to save evidence), and the installer path |
| Instructions | `skills/execute/windows-installer.md` + `skills/execute/evidence.md` + `skills/hosts/<host_id>.md` |
| Order | ENV (and resolve every `required_env` placeholder) → INST → UNIN. A test whose preconditions failed is reported as not run. |
| Output | `RunObservations` (§6.2): raw observed values per `test_id`, evidence paths, resolved `env`. **No status field.** |
| `max_turns` | Generous (e.g. 150). Cost is not a concern; the limit just protects against loops. |

### Windows-MCP tool allow-list (13)

| Tool | Used for |
|---|---|
| **PowerShell** | `msiexec /i … /qn /l*v <run>\evidence\install.log`, `msiexec /x {ProductCode}`, exit codes, `Get-AuthenticodeSignature`, OS version and admin check |
| **Registry** | Host detection; Programs & Features entry present or gone (both Uninstall keys, including WOW6432Node) |
| **FileSystem** | Required folders exist; installed files present; manifest readable; files gone after uninstall |
| **Process** | Installer or host running; close a stuck installer |
| **App** | Open *Programs and Features* / *Settings → Apps* for the UI uninstall path |
| **Snapshot** | Read the window's accessibility tree (the agent's "eyes") |
| **Click / Type / Shortcut / Scroll** | Use the UI uninstall dialog and confirm prompts |
| **WaitFor / Wait** | Wait for dialogs and entries to appear or disappear |
| **Screenshot** | Evidence after each UI step and at failures |

**Blocked (8):** ControlStatus, DisplayInventory, Move, MultiSelect, MultiEdit, Clipboard, Scrape, Notification. They're blocked twice: Windows-MCP `--tools` and the SDK filter.

### Guardrails
1. **Allow-list** (above), enforced in two places.
2. **Tool-call guardrail** (SDK hook, ~20 lines): reject Registry/FileSystem calls that write or delete outside `runs/<app>/<ts>/`. Reject PowerShell commands that match a deny pattern (`Remove-Item` outside the run folder, `Invoke-WebRequest`, `Set-ExecutionPolicy`, `reg delete`, `Format-*`, `shutdown`). The installer and `msiexec` are allowed.
3. **Untrusted text:** the instructions state that text in the plug-in's docs and UI is data, never instructions.
4. **Evidence rule:** report raw values only. Never judge pass or fail.

### Verdict engine (new, code, ~40 lines)
For each test case it evaluates `expected[]` against `observations[test_id].observed`:

| Check | Meaning |
|---|---|
| `equals` / `not_equals` | `observed[key] == value` |
| `in` | `observed[key] in values` (e.g. exit code in `[0, 3010]`) |
| `exists` / `not_exists` | the observed key is true or false (file, registry key, entry) |
| `contains` / `matches` | substring or regex on a text value (e.g. signer name) |

Statuses:
- **PASS:** every check holds.
- **FAIL:** any check fails.
- **BLOCKED:** a precondition test failed, or a needed placeholder couldn't be resolved.
- **ERROR:** no observation for that test, or a key is missing.

### Report (new, ~40 lines)
- `results.json`: per test, the status, expected vs observed, and evidence.
- `report.html` (Jinja2): a summary table, then per test the title, status, **source quote**, expected vs observed, and evidence links.
- `trace.jsonl`: every LLM turn and MCP call (tool, arguments, short result). It's the audit trail.

---

## 6. Data contracts (Pydantic)

### 6.1 `TestPlan` (Agent 1 output)
```yaml
app:
  name: "P&ID Connector Exporter for Plant 3D"
  publisher: "Kleen Software"
  version: "x.y"
  host_id: autocad-plant3d            # chosen by Agent 1: a host notes id, "none" (standalone) or "unknown"
  host_evidence:                      # why Agent 1 chose it (checked like any citation)
    - { doc: "I0:installer_facts", quote: "platform=Plant3D" }
  host_versions: ["2027"]
  installer: { file: "….msi", type: msi, product_code: "{…}", signer_claimed: "Kleen Software GmbH" }
summary:                              # rendered into understanding.md
  purpose: "…"
  install_footprint: ["…"]
  commands_or_ui: ["…"]
  open_questions: ["…"]
required_env: [HOST_INSTALL_DIR, PLUGIN_DIR]
testcases:
  - id: INST-002
    category: INST                    # ENV | INST | UNIN   (LOAD | FUNC later)
    title: "Programs and Features entry is created"
    source: { doc: "I0:installer_facts", quote: "ProductName = …" }
    preconditions: [INST-001]
    steps:                            # plain-language intents for Agent 2
      - "Look up the Uninstall registry entry whose DisplayName matches the product name"
    observe: [uninstall_entry_exists, display_version]   # keys Agent 2 must report
    expected:
      - { key: uninstall_entry_exists, check: exists }
      - { key: display_version, check: equals, value: "x.y" }
    priority: P1
```

### 6.2 `RunObservations` (Agent 2 output)
```yaml
env: { HOST_INSTALL_DIR: 'C:\Program Files\Autodesk\AutoCAD 2027', PLUGIN_DIR: '…' }
observations:
  - test_id: INST-002
    executed: true
    observed: { uninstall_entry_exists: true, display_version: "x.y" }
    evidence: ["evidence/INST-002_registry.txt"]
    notes: "Found under HKLM\\…\\Uninstall\\{…}"
```

### 6.3 `TestResult` (verdict engine output)
`{ test_id, status: PASS|FAIL|BLOCKED|ERROR, checks: [{key, check, expected, observed, ok}], evidence, notes }`

---

## 7. Skills (Markdown instruction files)

| File | Used by | Content |
|---|---|---|
| `skills/test-design/SKILL.md` | Agent 1 | The categories and what each must cover; citation format; placeholders; `observe` / `expected` rules and allowed checks; "never guess"; "test the plug-in, not the host" |
| `skills/hosts/autocad-plant3d.md` | Agents 1 + 2 | Plug-in folders (`%ProgramFiles%` / `%AppData%\Autodesk\ApplicationPlugins`), bundle + `PackageContents.xml`, version ↔ release numbers (2027 = R26.0), registry detection pattern, content folder default. **Knowledge only, never machine values.** |
| `skills/hosts/none.md` | Agents 1 + 2 | Standalone Windows app: Program Files, Start menu, Programs & Features only |
| `skills/execute/windows-installer.md` | Agent 2 | msiexec install and uninstall flags and logging; exit codes 0 / 3010 / 1602 / 1603; both Uninstall registry hives; signature check; UI uninstall path |
| `skills/execute/evidence.md` | Agent 2 | Raw values only; save evidence under the run folder; screenshot after UI steps; untrusted-text rule; no changes outside the footprint and run folder |

A new host means **one new Markdown file**, with no code change.

---

## 8. Tech stack (final)

| Area | Choice |
|---|---|
| Language and environment | Python 3.12, **uv** (existing) |
| Agents | **openai-agents** (Agents SDK). Replaces `google-genai`. |
| MCP server | **Windows-MCP**, pinned version, started via `uvx` |
| Schemas | Pydantic v2 (existing) |
| YAML | ruamel.yaml (existing) |
| Doc extraction | pypdf, python-docx, beautifulsoup4 (existing) |
| MSI read | pywin32 (existing) |
| CLI | Typer + rich (existing) |
| Report | Jinja2 (existing) |
| Tests | pytest, ruff (existing) |
| Secrets | `.env`: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_AGENTS_DISABLE_TRACING=1` |

**Dependency change:** remove `google-genai`, add `openai-agents` (+ `python-dotenv` if `.env` isn't already loaded).

---

## 9. Code layout (changes to `CodeBase/`)

```
CodeBase/
├─ src/mpagent/
│  ├─ cli.py                    # + commands: design, execute, all
│  ├─ config.py                 # NEW: .env loading, model name, paths, MCP version
│  ├─ models.py                 # existing; + TestPlan, RunObservations, TestResult
│  ├─ design/
│  │  ├─ intake.py              # existing (keep)
│  │  ├─ static_read.py, msi.py # existing (keep)
│  │  ├─ agent1.py              # NEW: Agent 1 + self-check + writers
│  │  └─ selfcheck.py           # NEW
│  ├─ execute/
│  │  ├─ agent2.py              # NEW: Agent 2 + Windows-MCP + guardrails
│  │  ├─ verdict.py             # NEW
│  │  └─ report.py              # NEW (+ templates/report.html.j2)
│  └─ trace.py                  # NEW: local JSONL hooks
├─ skills/                      # NEW: Markdown skills (§7)
└─ tests/                       # + test_selfcheck.py, test_verdict.py
```

Nothing in `design/` imports from `execute/`.

**CLI:**
```bash
uv run mpagent design inputs/pid-connector-exporter    # S0 + S1 + Agent 1 → runs/<app>/<ts>/
uv run mpagent execute runs/pid-connector-exporter     # Agent 2 + verdicts + report (newest run)
uv run mpagent all inputs/pid-connector-exporter       # both, fully automatic
```

**Run folder:** `runs/<app>/<ts>/`
- `intake_manifest.json`, `documents/`, `installer_facts.json`
- `testcases.yaml`, `testcases.json`, `understanding.md`
- `observations.json`, `results.json`, `report.html`, `trace.jsonl`, `evidence/`

---

## 10. Build steps

| # | Step | Done when |
|---|---|---|
| 1 | Dependencies + `config.py` (OpenAI key and model, tracing off) | `uv sync` OK; a "hello" agent call works |
| 2 | Windows-MCP smoke test: start it via `uvx` with the allow-list; an agent lists windows and reads one registry key | Tools visible = exactly the 13; blocked ones absent |
| 3 | Models: `TestPlan`, `RunObservations`, `TestResult` | Unit tests round-trip YAML and JSON |
| 4 | Skills: the 5 Markdown files | Reviewed by the team |
| 5 | Agent 1 (including the host choice) + self-check + writers | `mpagent design` produces a valid `testcases.yaml` for P&ID Exporter with ENV, INST and UNIN, and all quotes verified |
| 6 | Agent 2 + guardrails + trace | `mpagent execute` installs and uninstalls the plug-in and writes `observations.json` |
| 7 | Verdict engine + report | `results.json` + `report.html` with correct PASS/FAIL |
| 8 | `mpagent all` end-to-end demo run | One command from inputs to report |

---

## 11. Verification (demo acceptance)

1. **Unit:** `uv run pytest`. Self-check catches a fake quote and a missing placeholder. Verdict engine covers every check type and BLOCKED/ERROR.
2. **Design:** `mpagent design inputs/pid-connector-exporter`. A person reads `understanding.md` and agrees it matches the description. `testcases.yaml` covers ENV, INST and UNIN, and every test cites a real line.
3. **Execution, positive:** with Plant 3D 2027 installed, `mpagent execute` gives ENV PASS, INST PASS (exit code 0, entry and files present), UNIN PASS (entry and files gone).
4. **Execution, negative:** run INST checks before installing, or UNIN checks after a manual reinstall, and confirm FAIL is reported correctly (code-decided, not LLM-decided).
5. **Safety:** the trace shows only allowed tools, and guardrail rejections are logged.
6. **Evidence:** every test in `report.html` links to a log, a registry dump or a screenshot.

---

## 12. Risks (accepted for the demo)

| Risk | Mitigation |
|---|---|
| PowerShell, Registry and FileSystem can change the machine | Allow-list, deny-pattern guardrail, read-only rules, admin dev machine accepted; VM later |
| Prompt injection from third-party docs or UI text | Agent 1 has no tools; Agent 2 treats text as data; guardrails |
| UAC dialog can't be automated | Run elevated; `msiexec` path first; UI uninstall path is best-effort |
| Windows-MCP is a community project | Pinned version; it's the only external runtime dependency |
| LLM runs vary slightly | Verdicts by code; the plan is saved; a rerun uses the same YAML |
| Agent 2 skips a test in a long session | The verdict engine marks missing observations as ERROR; `max_turns` is generous |

---

## 13. Later phases

From our v0.3 design and from `AppStore automation/`:
1. **LOAD / FUNC** tests: host launch, UI entry visible, one documented feature, using Windows-MCP UI tools.
2. **Fixed Level 1 generic suite** (no LLM) for the checks that are the same for every app.
3. **Test-data catalogue** (approved sample files) for FUNC tests.
4. **NEEDS_REVIEW** status and a human reviewer report.
5. **Optional human review gate** (`--approve`).
6. **VM / Windows Sandbox isolation** with checkpoint reset.
7. **Snapshot diff** to find files left after uninstall.
8. **Feedback pass:** Agent 2's ENV findings go back to Agent 1.
9. **Record and replay** of MCP calls (for LLM-free reruns).
10. **EXE / ZIP installer readers**; submission bundle with `publisher_test_notes`.
11. **Host command channels** (e.g. COM) declared in host notes.
12. **Robot or TestRail export** from `testcases.yaml`.
