# mpagent: Marketplace Plug-in Validation Agents

An agent pipeline that reads an Autodesk Marketplace plug-in's description, documents and installer, then:
- **Agent 1** designs test cases and writes `understanding.md` and `testcases.yaml`. It never touches the machine.
- **Agent 2** runs those tests on a machine with the host installed. *(Not built yet.)*

For the design, see `../PROBLEM_STATEMENT.md`, `../ARCHITECTURE.md` and `../AGENT_FUNDAMENTALS.md`.

## Setup
1. Install `uv`: <https://docs.astral.sh/uv/>.
2. Install the dependencies:
   ```bash
   uv sync
   ```
   This installs Python 3.12 and every dependency into `.venv`, using the exact versions in `uv.lock`.
3. Paste your Gemini API key into `.env` (`GEMINI_API_KEY=...`). Keep that file private.

## Usage
```bash
uv run mpagent design inputs/pid-connector-exporter       # S0 + S1 as one workflow (what VS Run/F5 does)
uv run mpagent intake inputs/pid-connector-exporter       # Stage 0: sort files, extract text
uv run mpagent static-read runs/pid-connector-exporter    # Stage 1: read the installer (newest run)
uv run pytest                                             # unit tests
```

## Visual Studio 2026
1. Visual Studio Installer → Visual Studio Community 2026 → **Modify** → tick **Python development** → Modify.
2. Open `mpagent.sln`. The project uses the `.venv` interpreter, and F5 runs `mpagent intake inputs/pid-connector-exporter`.
3. Tests appear in **Test Explorer** (pytest).
4. Keep adding libraries from the terminal with `uv add <name>`, not from Visual Studio's package UI, so `uv.lock` stays in sync.

## Layout
```
src/mpagent/
  cli.py            command-line entry point
inputs/             one folder per plug-in (see inputs/README.md)
.env                Gemini API key (private)
```
More folders will be added as each stage is built.
