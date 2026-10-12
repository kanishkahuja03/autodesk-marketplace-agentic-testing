# mpagent: Marketplace App Validation Agents

A generic agent pipeline that reads a Windows plug-in's or app's documents and installer, then:
- **Agent 1** designs test cases and writes `understanding.md` and `testcases.yaml`. It never touches the machine. *(Not built yet.)*
- **Agent 2** runs those tests on this machine through Windows-MCP, and code decides PASS/FAIL. *(Not built yet.)*

For the design, see `../ARCHITECTURE.md` (source of truth) and `../ADR.md`.

## Setup
1. Install `uv`: <https://docs.astral.sh/uv/>.
2. Install the dependencies:
   ```bash
   uv sync
   ```
   This installs Python 3.12 and every dependency into `.venv`, using the exact versions in `uv.lock`.
3. Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and `OPENAI_MODEL`. Keep `.env` private.

## Usage
One command runs the whole pipeline into a new folder `runs/<app>/<timestamp>/`. There are no sub-commands.
```bash
uv run mpagent inputs/pid-connector-exporter
uv run pytest                                  # unit tests
```
Each run writes `run.log`. Its last line is `COMPLETED: …` (exit 0), `STOPPED: …` (exit 1) or `CRASHED: …` (exit 2).
Built so far: S0 intake and S1 installer static read.

## Visual Studio 2026
1. Visual Studio Installer → Visual Studio Community 2026 → **Modify** → tick **Python development** → Modify.
2. Open `mpagent.sln`. The project uses the `.venv` interpreter, and **F5 runs the full pipeline** for `inputs/pid-connector-exporter`. To test another app, change the launch argument in the project properties.
3. Tests appear in **Test Explorer** (pytest).
4. Keep adding libraries from the terminal with `uv add <name>`, not from Visual Studio's package UI, so `uv.lock` stays in sync.

## Layout
```
src/mpagent/
  cli.py            single entry point (F5 / uv run mpagent <input_dir>)
  pipeline.py       runs every step in order, writes the final status line
  config.py         settings from .env
  runlog.py         run.log (+ console) and trace.jsonl
  design/           S0 intake, S1 installer static read
inputs/             one folder per app (see inputs/README.md)
.env                OpenAI settings (private; template: .env.example)
```
More folders will be added as each step is built.
