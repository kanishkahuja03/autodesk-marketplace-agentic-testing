# Specification (engineering)

Normative requirements for the PoC. Narrative and options live in the base `.docx`; this file is the **testable** contract.

## Submission contract

Each certification run is keyed by `submission_id`. Required inputs:

| Field | Type | Description |
|-------|------|-------------|
| `submission_id` | string | Unique run identifier |
| `host_product` | string | PoC: `"Plant3D"` |
| `host_versions` | string[] | Supported Plant 3D versions (e.g. `["2025"]`) |
| `package_path` | path | Installer or bundle (MSI/EXE/etc.) |
| `documentation` | path[] | Publisher docs (PDF, HTML, markdown) |
| `metadata` | object | Name, publisher, package type, optional dependencies |
| `publisher_test_notes` | string (optional) | Reviewer/publisher-supplied scenarios |

PoC location: `submissions/<submission_id>/` with `metadata.json`, `package/`, `docs/`.

## Run outcomes

| Status | Meaning |
|--------|---------|
| **Pass** | Deterministic checks satisfied; evidence recorded |
| **Fail** | Tool error, install/launch failure, or check mismatch |
| **Needs human review** | Steps executed but correctness not deterministically verifiable |

Final marketplace certification remains a **human reviewer** decision.

## Test levels

### Level 1 — Generic (mandatory per run)

Product-agnostic checks executed for every submission. Initial PoC set (5–10):

1. Package/installer validation (structure, exit code)
2. Installation success
3. Application launch (Plant 3D)
4. Add-in / plugin load detection
5. UI presence (ribbon tab or documented entry point—publisher checklist)
6. Startup stability (open approved golden DWG, idle window, no fatal dialog)
7. Uninstall / clean removal (optional in first sprint; required before PoC sign-off)

### Level 2 — Plant 3D / AutoCAD capabilities

Reusable tools (not per-app code paths). See [PLANT3D.md](./PLANT3D.md).

### Level 3 — App-specific

Derived from **this submission’s** documentation. AI may propose steps; orchestrator validates against allow-list and test-data catalogue. High-impact or ambiguous tests → **Needs human review** unless reviewer pre-approves a template.

## Tool layer

Tools are implemented in code; the AI invokes them by name with JSON arguments.

### Initial allow-list (~10–15)

| Tool | Purpose |
|------|---------|
| `launch_application` | Start Plant 3D |
| `close_application` | Graceful shutdown |
| `open_drawing` | Open approved DWG from catalogue |
| `run_command` | Send AutoCAD command string |
| `wait_for_idle` | Command / document idle with timeout |
| `capture_screenshot` | Window capture for evidence |
| `collect_logs` | Copy known log paths |
| `verify_file_exists` | Export/output presence |
| `verify_file_contains` | Text/header validation |
| `install_plugin` | Run submission installer |
| `uninstall_plugin` | Remove add-in |
| `verify_plugin_loaded` | Load detection per SME method |
| `reset_environment` | Snapshot restore or cleanup script |

Forbidden: arbitrary shell, unrestricted filesystem, network (unless explicitly allow-listed later).

## Test data

- Stored under `test_data/` with metadata (product version, discipline P&ID vs 3D, allowed operations).
- AI may **suggest** dataset IDs; orchestrator must reject IDs not in the catalogue.
- Expected outputs (hashes, snippets) stored for deterministic Level 3 checks where available.

## Evidence bundle

Per run: `runs/<run_id>/` containing `manifest.json`, generic and app-specific results, `screenshots/`, `logs/`, exports, optional `agent_trace.jsonl`, `report.html`.

## Safety

- Isolated Windows VM or equivalent.
- Tool allow-list enforced in code before execution.
- Sandbox paths for file operations.
- No production marketplace actions from automation.

## PoC samples

- **Host:** Plant 3D, one version.
- **Apps:** 1–2 representative plugins (TBD with review team).
- **AI workflows:** 1–3 documented flows per sample app where deterministic verification exists or evidence-only review is acceptable.
