"""Command-line entry point: `uv run mpagent <command>`."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from mpagent import __version__
from mpagent.design.intake import IntakeError, run_intake
from mpagent.design.msi import MsiError
from mpagent.design.static_read import StaticReadError, latest_run, run_static_read
from mpagent.models import InstallerFacts, IntakeManifest

app = typer.Typer(help="Marketplace plug-in validation agents.", no_args_is_help=True)
console = Console()


@app.command()
def version() -> None:
    """Print the mpagent version."""
    typer.echo(__version__)


@app.command()
def design(
    plugin_dir: Annotated[Path, typer.Argument(help="inputs/<plugin> folder")],
    runs_dir: Annotated[Path, typer.Option(help="Where run folders are created")] = Path("runs"),
) -> None:
    """Design side as one workflow: S0 intake -> S1 installer static read (Agent 1 will follow)."""
    console.rule("[bold]S0 Intake[/bold]")
    try:
        manifest, run_dir = run_intake(plugin_dir, runs_dir)
    except IntakeError as e:
        console.print(f"[red]Intake failed:[/red] {e}")
        raise typer.Exit(code=1)
    _print_intake(manifest)

    console.rule("[bold]S1 Installer static read[/bold]")
    try:
        facts = run_static_read(run_dir)
    except (StaticReadError, MsiError) as e:
        console.print(f"[red]Static read failed:[/red] {e}")
        raise typer.Exit(code=1)
    _print_static_read(facts)

    console.print(f"\nRun folder: [green]{run_dir}[/green]")


@app.command()
def intake(
    plugin_dir: Annotated[Path, typer.Argument(help="inputs/<plugin> folder")],
    runs_dir: Annotated[Path, typer.Option(help="Where run folders are created")] = Path("runs"),
) -> None:
    """S0 only: classify input files, extract document text, record installer facts."""
    try:
        manifest, run_dir = run_intake(plugin_dir, runs_dir)
    except IntakeError as e:
        console.print(f"[red]Intake failed:[/red] {e}")
        raise typer.Exit(code=1)
    _print_intake(manifest)
    console.print(f"\nSaved to: [green]{run_dir}[/green]")


@app.command("static-read")
def static_read(
    run: Annotated[Path, typer.Argument(help="A run folder from S0, or runs/<plugin> to use its newest run")],
) -> None:
    """S1 only: read the installer's contents without running it."""
    try:
        run_dir = latest_run(run)
        facts = run_static_read(run_dir)
    except (StaticReadError, MsiError) as e:
        console.print(f"[red]Static read failed:[/red] {e}")
        raise typer.Exit(code=1)
    _print_static_read(facts)
    console.print(f"\nSaved to: [green]{run_dir / 'installer_facts.json'}[/green]")


def _print_intake(manifest: IntakeManifest) -> None:
    files = Table(title=f"Input files: {manifest.plugin}")
    files.add_column("File")
    files.add_column("Kind")
    files.add_column("Size", justify="right")
    for f in manifest.files:
        files.add_row(f.name, f.kind.value, f"{f.size_bytes:,} B")
    console.print(files)

    docs = Table(title="Extracted documents")
    for col in ("ID", "Source", "Lines", "Chars", "Text file"):
        docs.add_column(col)
    for d in manifest.documents:
        docs.add_row(d.doc_id, d.source_file, str(d.line_count), str(d.char_count), d.text_file)
    console.print(docs)

    inst = manifest.installer
    console.print(f"Installer: [bold]{inst.file}[/bold] ({inst.type})")
    console.print(f"Claimed signer: {inst.signer_name or '-'}")
    console.print(f"Estimated document tokens: {manifest.estimated_tokens:,}")
    for w in manifest.warnings:
        console.print(f"[yellow]Warning:[/yellow] {escape(w)}")


def _print_static_read(facts: InstallerFacts) -> None:
    p = facts.properties
    console.print(f"[bold]{p.get('ProductName', facts.installer_file)}[/bold] {p.get('ProductVersion', '')}")
    console.print(f"Manufacturer: {p.get('Manufacturer', '-')}   ProductCode: {p.get('ProductCode', '-')}")
    console.print(f"Install scope: {facts.install_scope or '-'}   Files: {len(facts.files)}")
    for root in facts.install_roots:
        console.print(f"  installs under: {root}")

    for b in facts.bundles:
        console.print(f"\n[bold]PackageContents.xml[/bold] ({b.install_path or b.source})")
        console.print(f"  {b.name} {b.app_version or ''} by {b.company_name or b.author or '-'}")
        for rr in b.runtime_requirements:
            line = f"  requires ({rr.scope}): platform={rr.platform or '-'} series={rr.series_min or '?'}..{rr.series_max or '?'}"
            console.print(escape(line))
        commands = [c.global_name for comp in b.components for c in comp.commands if c.global_name]
        console.print(f"  components: {len(b.components)}   commands: {', '.join(commands) or 'none listed'}")

    if facts.custom_actions:
        runs_code = [a for a in facts.custom_actions if "runs" in a.kind]
        console.print(f"\nCustom actions: {len(facts.custom_actions)} ({len(runs_code)} run code)")
        for a in runs_code:
            console.print(escape(f"  {a.name}: {a.kind} {('(' + ', '.join(a.flags) + ')') if a.flags else ''}"))
    for d in facts.embedded_documents:
        console.print(f"Embedded document {d.doc_id}: {d.name} ({d.line_count} lines) -> {d.text_file}")
    for n in facts.notable_files:
        console.print(f"[magenta]Notable:[/magenta] {escape(n)}")
    for w in facts.warnings:
        console.print(f"[yellow]Warning:[/yellow] {escape(w)}")


if __name__ == "__main__":
    app()
