"""The full pipeline behind the single entry point (ARCHITECTURE.md D16).

S0 intake -> S1 installer static read -> (Agent 1 -> preflight -> Agent 2 -> verdict -> report -> cleanup:
added in later build steps). Every run gets its own run folder with run.log and a final status line:
COMPLETED (exit 0), STOPPED (exit 1) or CRASHED (exit 2).
"""

from pathlib import Path

from mpagent.config import ConfigError, Settings, load_settings
from mpagent.design.intake import IntakeError, run_intake
from mpagent.design.msi import MsiError
from mpagent.design.static_read import StaticReadError, run_static_read
from mpagent.models import InstallerFacts, IntakeManifest
from mpagent.runlog import attach_run_folder, log, start_logging, stop_logging

EXIT_COMPLETED = 0
EXIT_STOPPED = 1
EXIT_CRASHED = 2


class PipelineStopped(Exception):
    """A step decided the run cannot continue; the message is the STOPPED reason."""


def run(input_dir: Path, runs_dir: Path | None = None) -> int:
    """Run the whole pipeline for one input folder and return the process exit code."""
    start_logging()
    run_dir: Path | None = None
    try:
        settings = load_settings()
        log.info("RUN: input %s", input_dir.resolve())
        run_dir = _design_side(input_dir, runs_dir or settings.runs_dir, settings)
        log.info("COMPLETED: S0 + S1 done; Agent 1 and the execution side are not built yet. Run folder: %s", run_dir)
        return EXIT_COMPLETED
    except PipelineStopped as e:
        log.error("STOPPED: %s%s", e, _no_run_folder_note(run_dir))
        return EXIT_STOPPED
    except Exception:  # noqa: BLE001 - any unexpected error must still end with a CRASHED line and exit 2
        log.exception("CRASHED: unexpected error%s", _no_run_folder_note(run_dir))
        return EXIT_CRASHED
    finally:
        stop_logging()


def _no_run_folder_note(run_dir: Path | None) -> str:
    return "" if run_dir else " (no run folder was created, so there is no run.log)"


def _design_side(input_dir: Path, runs_dir: Path, settings: Settings) -> Path:
    """S0 and S1. Returns the run folder. Nothing on the machine is inspected here."""
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

    try:
        settings.require_openai()
    except ConfigError as e:
        log.warning("Agent 1 will need OpenAI settings: %s", e)
    return run_dir


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
