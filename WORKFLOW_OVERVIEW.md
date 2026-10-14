# Workflow Overview: Marketplace App Validation Agents

> A short summary for reviewers. Status as of 2026-10-14. For details, see `ARCHITECTURE.md` and `ADR.md`.

**In one line:** a person drops an app's documents and installer into a folder and presses **F5**. **Agent 1 (LLM)** reads the documents and designs the tests. **Agent 2 (LLM)** runs them on the machine through **Windows-MCP**. **Code** decides PASS or FAIL and writes the report.

---

## 1. Workflow

```
inputs/<app>/  (description .txt, user guide, installer .msi)       ← chosen by the F5 argument
   │
S0  Intake ................ code    sort files by type, extract text → D1, D2…
S1  Installer read ........ code    read the MSI without running it → F1 (facts), I1 (Help.html)
A1  Agent 1 ............... LLM     evidence + skills → choose host → testcases.yaml
    Self-check ............ code    quotes real? required tests present? → retry ≤ 2
    Review ................ human   y/n in the console before anything touches the machine
P   Preflight ............. code    admin? Windows-MCP ok? app not installed yet (ENV-000)? host closed?
A2  Agent 2 ............... LLM     runs the tests through Windows-MCP: ENV → INST → LOAD → UNIN
    Kill host + cleanup ... code    close the host; uninstall if the app is still installed
V   Verdict + report ...... code    expected vs observed → PASS / FAIL / BLOCKED / ERROR
   │
runs/<app>/<timestamp>/  run.log, testcases.yaml, understanding.md, results.json, report.html, evidence/
```

| Stage | What happens |
|---|---|
| **S0 Intake** | The input folder comes from the F5 argument (`inputs/pid-connector-exporter`) or from `uv run mpagent inputs/<app>`. Files are sorted **by extension**, and exactly one installer must be present. The **installer path is neither hard-coded nor searched for on the machine**: it is `inputs/<app>/<installer>`, and code passes it to Agent 2. Text is extracted from every document, with numbered lines. |
| **S1 Installer read** | Opens the MSI read-only and records the facts: ProductCode, name, version, install folder (`%AppData%\Autodesk\ApplicationPlugins\…`), files, signer, and the plug-in manifest (`platform = Plant3D`). |
| **Agent 1** (no tools) | Gets the **skills** (`test-design/SKILL.md` plus every host notes file, e.g. `hosts/autocad-plant3d.md`, `hosts/none.md`) and the evidence (D1, D2, I1, F1). The **LLM decides the host app** from that evidence and must cite its reason, e.g. `F1: platform = Plant3D`. It then writes the test cases. Code checks every quote and the required tests. |
| **Preflight** | Code checks that the process is elevated, that Windows-MCP offers exactly 13 tools, that the app is **not** installed yet (ENV-000), and that the host isn't running. |
| **Agent 2** (Windows-MCP) | **Windows-MCP is the hands and eyes**: it reads the screen as a UI tree (`Snapshot`), clicks and types, and reads the registry and files. **The LLM decides each next action**, and **code guardrails** check every call: PowerShell must start with an allowed command; Registry and FileSystem are read-only; the installer runs only once; App may start only the host. The **host executable is found by code** from the registry rules in the host notes (e.g. `AcadLocation` → `acad.exe /product PLNT3D`). Agent 2 may start only that program. |
| **Verdict + report** | Code compares each observed value with the expected one. The LLM never sets PASS or FAIL. |

**Who decides what:** the LLM chooses the host, the tests, and each action on screen. Code fixes the paths, checks every tool call, and decides the verdicts.

## 2. Test cases: order, data and current status

**Order:** each test lists the tests that must PASS first (preconditions). If one fails, the tests depending on it are BLOCKED. UNIN always runs.

| Group | Tests (latest plan) | Run by | Checks |
|---|---|---|---|
| ENV | ENV-000 (built in), ENV-001, ENV-002 | code / Agent 2 | App not installed yet; Plant 3D found in the registry; version 2027 (R26.0) |
| INST | INST-001 … 004 | Agent 2 | Silent `msiexec /i`, exit code from the log; Uninstall entry; bundle folder, `PackageContents.xml`, the DLLs |
| LOAD | LOAD-000 (built in), LOAD-001 | Agent 2, decided from the UI tree | Plant 3D starts with a new drawing; the **"P&ID Exporter"** ribbon tab is visible |
| UNIN | UNIN-001 … 003 | Agent 2 | Silent `msiexec /x`, exit code; entry removed; files removed |

**Data the tests run with:**
- the real installer `KleenSoftwareGmbHPIDConnectorExporterPlant3D.msi` (P&ID Connector Exporter 1.0.5);
- its ProductCode and names, taken from the installer facts;
- AutoCAD Plant 3D 2027 on the dev machine, run as administrator;
- the OpenAI model set in `.env`;
- machine paths (`${HOST_INSTALL_DIR}`, `${PLUGIN_DIR}`), filled in by Agent 2 during ENV.

**Latest run, 2026-10-14 11:18 (`runs/…/20261014-111858`): 10 PASS, 1 FAIL, 1 BLOCKED.**
- ENV, INST and UNIN all **PASS**: installs, registers and uninstalls cleanly, with no files left behind.
- **LOAD-000 FAIL:**
  - Plant 3D started, but the plug-in showed a German notice: *"Hinweis: works only together with the P&ID Connector Importer"*.
  - Agent 2 stopped there, on the Start page, without opening a new drawing.
  - So **LOAD-001 (the ribbon tab check) was BLOCKED**.
  - **Next:** Agent 2 should acknowledge this notice and continue. The host-interaction skill already says so; this run didn't follow it.

---

## 3. For production: moving Agent 1 from skill files to an MCP server

**Why:** today, every host notes file is pasted into Agent 1's prompt. That works for 2 hosts but won't scale to hundreds of hosts or long manuals.

**Proposal:**
- **A read-only "Test-Design Knowledge" MCP server.** Agent 1 fetches only what it needs.
- **Still no machine access.** This server only serves knowledge and plan checks; it is never Windows-MCP.
- **Code keeps the final self-check.**

```
mcp/test-design-knowledge/
├─ server.py                  # read-only, versioned
├─ resources/
│  ├─ skills/test-design.md
│  └─ hosts/  index.yaml, autocad-plant3d.md, none.md, <new-host>.md
├─ tools/
│  ├─ list_hosts / get_host_notes      # fetch one host instead of all
│  ├─ search_evidence / get_evidence   # large manuals, on demand
│  └─ check_plan                       # self-check during the run
└─ prompts/design_test_plan.md
```

**Steps:**
1. Serve today's files unchanged.
2. Replace the full catalogue with `index.yaml` plus `get_host_notes`.
3. Add the evidence search tools.
4. Add `check_plan`.
5. Add auth, versioning and an audit log for production.

**Trade-off:** it scales and keeps knowledge in one shared place, at the cost of one more service to run and secure.
