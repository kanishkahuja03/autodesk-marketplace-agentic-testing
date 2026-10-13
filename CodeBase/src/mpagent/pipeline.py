"""The full pipeline behind the single entry point (ARCHITECTURE.md D16).

S0 intake -> S1 installer static read -> Agent 1 -> preflight -> Agent 2 -> cleanup -> verdicts -> report
(the last three always run once Agent 2 has started). Every run gets its own run folder with run.log and a
final status line: COMPLETED (exit 0), STOPPED (exit 1) or CRASHED (exit 2).
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from mpagent.config import ConfigError, Settings, load_settings
from mpagent.design.agent1 import Agent1Error, AskFn, design_tests, openai_ask
from mpagent.design.intake import IntakeError, run_intake
from mpagent.design.msi import MsiError
from mpagent.design.static_read import StaticReadError, run_static_read
from mpagent.execute.agent2 import Agent2Error, run_agent2
from mpagent.execute.cleanup import cleanup
from mpagent.execute.observations import load_observations
from mpagent.execute.preflight import PreflightError, run_preflight
from mpagent.execute.report import REPORT_FILE, summary_line, write_report
from mpagent.models import InstallerFacts, IntakeManifest, RunResults, TestPlan
from mpagent.runlog import (
    attach_run_folder,
    log,
    run_log_attached,
    start_logging,
    stop_logging,
)

EXIT_COMPLETED = 0
EXIT_STOPPED = 1
EXIT_CRASHED = 2


class PipelineStopped(Exception):
    """A step decided the run cannot continue; the message is the STOPPED reason."""


@dataclass(frozen=True)
class Design:
    """What the design side hands to the execution side."""

    run_dir: Path
    manifest: IntakeManifest
    facts: InstallerFacts
    plan: TestPlan

    @property
    def installer_path(self) -> Path:
        return Path(self.manifest.input_dir) / self.manifest.installer.file


def run(input_dir: Path, runs_dir: Path | None = None, agent1_ask: AskFn | None = None) -> int:
    """Run the whole pipeline for one input folder and return the process exit code.
    `agent1_ask` replaces the real LLM call (unit tests only)."""
    start_logging()
    try:
        settings = load_settings()
        log.info("RUN: input %s", input_dir.resolve())
        design = _design_side(input_dir, runs_dir or settings.runs_dir, settings, agent1_ask)
        _preflight(design.run_dir, design.facts, settings)
        run_results = _execution_side(design, settings)
        if run_results is None:
            raise PipelineStopped("the report could not be written (see the error above)")
        log.info("COMPLETED: %s — report: %s", summary_line(run_results), design.run_dir / REPORT_FILE)
        return EXIT_COMPLETED
    except PipelineStopped as e:
        log.error("STOPPED: %s%s", e, _no_run_folder_note())
        return EXIT_STOPPED
    except Exception:  # noqa: BLE001 - any unexpected error must still end with a CRASHED line and exit 2
        log.exception("CRASHED: unexpected error%s", _no_run_folder_note())
        return EXIT_CRASHED
    finally:
        stop_logging()


def _no_run_folder_note() -> str:
    return "" if run_log_attached() else " (no run folder was created, so there is no run.log)"


def _preflight(run_dir: Path, facts: InstallerFacts, settings: Settings) -> None:
    """Code checks before Agent 2 (D20). Runs after Agent 1, so Agent 1 stays blind."""
    log.info("Preflight: start")
    try:
        run_preflight(run_dir, facts, settings)
    except PreflightError as e:
        raise PipelineStopped(f"preflight: {e} — Agent 2 not started") from e
    log.info("Preflight: done")


def _execution_side(design: Design, settings: Settings) -> RunResults | None:
    """Agent 2, then (in `finally`, whatever happened) cleanup (D28) and verdicts + report (D19, D29)."""
    log.info("Agent 2 test execution: start")
    run_results: RunResults | None = None
    try:
        run_agent2(design.plan, design.run_dir, design.installer_path, settings)
        log.info("Agent 2 test execution: done")
    except Agent2Error as e:
        raise PipelineStopped(f"Agent 2 didn't finish: {e}") from e
    finally:
        _log_missing_observations(design)
        try:
            cleanup(design.run_dir, design.facts)
        except Exception as e:  # noqa: BLE001 - cleanup must never hide the real outcome
            log.error("CLEANUP: failed with %s: %s — manual cleanup may be needed", type(e).__name__, e)
        run_results = _verdicts_and_report(design)
    return run_results


def _verdicts_and_report(design: Design) -> RunResults | None:
    log.info("Verdicts and report: start")
    try:
        run_results = write_report(design.plan, design.run_dir)
    except Exception as e:  # noqa: BLE001 - a report problem must not hide the Agent 2 outcome
        log.error("REPORT: failed with %s: %s", type(e).__name__, e)
        return None
    for r in run_results.results:
        log.info("  %-8s %-7s %s", r.test_id, r.status.value, r.notes or "")
    log.info("Verdicts and report: done -> results.json, report.html")
    return run_results


def _log_missing_observations(design: Design) -> None:
    recorded = {o.test_id for o in load_observations(design.run_dir)}
    missing = [t.id for t in design.plan.testcases if t.id not in recorded]
    log.info("  observations: %d of %d tests recorded%s", len(design.plan.testcases) - len(missing),
             len(design.plan.testcases), f"; missing: {', '.join(missing)}" if missing else "")


def _design_side(input_dir: Path, runs_dir: Path, settings: Settings, agent1_ask: AskFn | None) -> Design:
    """S0, S1 and Agent 1. Nothing on the machine is inspected here."""
    log.info("S0 intake: start")
    try:
        manifest, run_dir = run_intake(input_dir, runs_dir)
    except IntakeError as e:
        raise PipelineStopped(f"S0 intake failed: {e}") from e
    attach_run_folder(run_dir)
    log.info("run folder: %s", run_dir)
    _log_intake(manifest)
    log.info("S0 intake: done")

    log.info("S1 installer static read: start")
    try:
        facts = run_static_read(run_dir)
    except (StaticReadError, MsiError) as e:
        raise PipelineStopped(f"S1 installer static read failed: {e}") from e
    _log_static_read(facts)
    log.info("S1 installer static read: done")

    log.info("Agent 1 test design: start")
    try:
        ask = agent1_ask or openai_ask(settings)
        plan = design_tests(run_dir, manifest, facts, ask)
    except ConfigError as e:
        raise PipelineStopped(f"Agent 1 can't start: {e}") from e
    except Agent1Error as e:
        raise PipelineStopped(f"Agent 1 failed: {e} — Agent 2 not started") from e
    counts = Counter(t.category.value for t in plan.testcases)
    log.info("  host: %s; tests: %s; open questions: %d", plan.app.host_id,
             ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), len(plan.summary.open_questions))
    log.info("Agent 1 test design: done -> testcases.yaml, understanding.md")
    return Design(run_dir, manifest, facts, plan)


def _log_intake(manifest: IntakeManifest) -> None:
    for f in manifest.files:
        log.info("  file: %s (%s, %s bytes)", f.name, f.kind.value, f"{f.size_bytes:,}")
    for d in manifest.documents:
        log.info("  document %s: %s, %d lines -> %s", d.doc_id, d.source_file, d.line_count, d.text_file)
    log.info("  installer: %s (%s), claimed signer: %s", manifest.installer.file, manifest.installer.type,
             manifest.installer.signer_name or "-")
    log.info("  estimated document tokens: %s", f"{manifest.estimated_tokens:,}")
    for w in manifest.warnings:
        log.warning("  %s", w)


def _log_static_read(facts: InstallerFacts) -> None:
    p = facts.properties
    log.info("  product: %s %s by %s", p.get("ProductName", facts.installer_file), p.get("ProductVersion", ""),
             p.get("Manufacturer", "-"))
    log.info("  ProductCode: %s, install scope: %s, files: %d", p.get("ProductCode", "-"), facts.install_scope or "-",
             len(facts.files))
    for root in facts.install_roots:
        log.info("  installs under: %s", root)
    for b in facts.bundles:
        commands = [c.global_name for comp in b.components for c in comp.commands if c.global_name]
        log.info("  bundle manifest: %s %s, components: %d, commands: %s", b.name, b.app_version or "",
                 len(b.components), ", ".join(commands) or "none listed")
    for d in facts.embedded_documents:
        log.info("  embedded document %s: %s (%d lines) -> %s", d.doc_id, d.name, d.line_count, d.text_file)
    for n in facts.notable_files:
        log.info("  notable: %s", n)
    for w in facts.warnings:
        log.warning("  %s", w)
