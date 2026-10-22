"""The full pipeline behind the single entry point (ARCHITECTURE.md D16).

S0 intake -> S1 installer static read -> Agent 1 -> review of the test cases (y/n in the console) -> preflight
-> Agent 2 -> kill host -> cleanup -> verdicts -> report (the last four always run once Agent 2 has started). Every run gets its own run folder with run.log and a
final status line: COMPLETED (exit 0), STOPPED (exit 1) or CRASHED (exit 2).
"""

import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mpagent.config import ConfigError, Settings, load_settings
from mpagent.design.agent1 import Agent1Error, AskFn, design_tests, openai_ask
from mpagent.design.intake import IntakeError, run_intake
from mpagent.design.msi import MsiError
from mpagent.design.samples import list_samples
from mpagent.design.static_read import StaticReadError, run_static_read
from mpagent.execute.agent2 import Agent2Error, run_agent2
from mpagent.execute.cleanup import cleanup
from mpagent.execute.footprint import record_unin000
from mpagent.execute.host import CRASH_EVENTS_FILE, kill_host, save_crash_events
from mpagent.execute.observations import load_observations, save_observation
from mpagent.execute.preflight import PreflightError, run_preflight
from mpagent.execute.report import REPORT_FILE, summary_line, write_report
from mpagent.hostnotes import host_process
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


# (question) -> True to continue; None = ask in the console when there is one (LOAD_TESTS_PLAN.md L19)
ConfirmFn = Callable[[str], bool]


def run(input_dir: Path, runs_dir: Path | None = None, agent1_ask: AskFn | None = None,
        confirm: ConfirmFn | None = None) -> int:
    """Run the whole pipeline for one input folder and return the process exit code.
    `agent1_ask` replaces the real LLM call and `confirm` the console question (unit tests only)."""
    start_logging()
    try:
        settings = load_settings()
        log.info("RUN: input %s", input_dir.resolve())
        design = _design_side(input_dir, runs_dir or settings.runs_dir, settings, agent1_ask)
        _review(design, confirm)
        _preflight(design, settings)
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


REVIEW_QUESTION = "Review the test cases above (testcases.yaml). Go ahead and run them on this machine? [y/n]: "


def console_confirm(question: str) -> bool:
    """Ask y/n in the console until the answer is y or n. Ctrl+C or end of input counts as n."""
    while True:
        try:
            answer = input(question).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def _review(design: Design, confirm: ConfirmFn | None) -> None:
    """Show the test cases and wait for the user's go-ahead before anything touches the machine (L19).
    Without a console (e.g. unit tests), the run continues and the log says so."""
    log.info("Test case review: please check the test plan before it runs")
    log.info("  test cases: %s", design.run_dir / "testcases.yaml")
    log.info("  summary:    %s", design.run_dir / "understanding.md")
    for t in design.plan.testcases:
        log.info("  %-9s %-4s %s %s", t.id, t.category.value, t.priority.value, t.title)
    if confirm is None:
        if not sys.stdin or not sys.stdin.isatty():
            log.info("Test case review: no console to ask in; continuing")
            return
        confirm = console_confirm
    if not confirm(REVIEW_QUESTION):
        raise PipelineStopped("test plan not approved at the review — nothing was installed")
    log.info("Test case review: approved")


def _preflight(design: Design, settings: Settings) -> None:
    """Code checks before Agent 2 (D20). Runs after Agent 1, so Agent 1 stays blind."""
    log.info("Preflight: start")
    try:
        run_preflight(design.run_dir, design.facts, settings, host_process(design.plan.app.host_id))
    except PreflightError as e:
        raise PipelineStopped(f"preflight: {e} — Agent 2 not started") from e
    log.info("Preflight: done")


def _execution_side(design: Design, settings: Settings) -> RunResults | None:
    """Agent 2, then (in `finally`, whatever happened) kill the host, cleanup (D28) and verdicts + report (D19, D29).
    The host is killed before cleanup, so an uninstall never runs under it (LOAD_TESTS_PLAN.md L12)."""
    log.info("Agent 2 test execution: start")
    started = datetime.now().astimezone()
    run_results: RunResults | None = None
    try:
        run_agent2(design.plan, design.run_dir, design.installer_path, settings, design.facts)
        log.info("Agent 2 test execution: done")
    except Agent2Error as e:
        raise PipelineStopped(f"Agent 2 didn't finish: {e}") from e
    finally:
        _log_missing_observations(design)
        _kill_host(design, started)
        _check_leftovers(design)
        try:
            cleanup(design.run_dir, design.facts)
        except Exception as e:  # noqa: BLE001 - cleanup must never hide the real outcome
            log.error("CLEANUP: failed with %s: %s — manual cleanup may be needed", type(e).__name__, e)
        run_results = _verdicts_and_report(design, settings)
    return run_results


def _kill_host(design: Design, started: datetime) -> None:
    """Kill the host (before cleanup), then save any host crash records Windows wrote during Agent 2."""
    hp = host_process(design.plan.app.host_id)
    if hp is None:
        return
    try:
        killed = kill_host(hp.processes)
        log.info("HOST: %s", f"killed {len(killed)} process(es)" if killed else "not running")
        crashes = save_crash_events(design.run_dir, hp.processes, started)
    except Exception as e:  # noqa: BLE001 - must never hide the real outcome
        log.error("HOST: kill/crash check failed with %s: %s — close the host by hand", type(e).__name__, e)
        return
    for c in crashes:
        log.warning("HOST CRASH: %s", c.splitlines()[0] + " " + " ".join(c.splitlines()[1:3]))
    if crashes:
        log.warning("HOST: %d crash record(s) saved to %s", len(crashes), CRASH_EVENTS_FILE)


def _check_leftovers(design: Design) -> None:
    """UNIN-000: compare the footprint with the preflight's baseline, after the host was closed and before cleanup."""
    hp = host_process(design.plan.app.host_id)
    try:
        obs = record_unin000(design.run_dir, design.facts.install_roots, hp.profile_ignore if hp else [])
    except Exception as e:  # noqa: BLE001 - must never hide the real outcome
        log.error("LEFTOVERS: check failed with %s: %s", type(e).__name__, e)
        return
    if obs is None:
        return
    save_observation(design.run_dir, obs)
    log.info("  UNIN-000 observed: %s", ", ".join(f"{kv.key}={kv.value!r}" for kv in obs.observed))
    for f in obs.findings:
        log.warning("  %s", f)


def _verdicts_and_report(design: Design, settings: Settings | None = None) -> RunResults | None:
    log.info("Verdicts and report: start")
    try:
        run_results = write_report(design.plan, design.run_dir, settings)
    except Exception as e:  # noqa: BLE001 - a report problem must not hide the Agent 2 outcome
        log.error("REPORT: failed with %s: %s", type(e).__name__, e)
        return None
    for r in run_results.results:
        log.info("  %-8s %-7s %s", r.test_id, r.status.value, r.notes or "")
    for r in run_results.results:  # e.g. documentation mismatches found by the judge (D63)
        for f in r.findings:
            log.warning("  FINDING %s: %s", r.test_id, f)
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
        samples = list_samples(settings.samples_dir)
        log.info("  samples: %s", ", ".join(s.name for s in samples) or "none (SAMPLES_DIR not set or empty)")
        inputs = list_samples(settings.input_files)
        log.info("  input files: %s", ", ".join(s.name for s in inputs) or "none (INPUT_FILES not set or empty)")
        plan = design_tests(run_dir, manifest, facts, ask, samples, inputs)
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
