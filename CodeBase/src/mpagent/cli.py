"""Single entry point (ARCHITECTURE.md D16, D17): `uv run mpagent inputs/<app>`, or F5 in Visual Studio.

There are no sub-commands: every run executes the full pipeline into a new run folder.
"""

from pathlib import Path
from typing import Annotated

import typer

from mpagent import __version__
from mpagent.pipeline import run

app = typer.Typer(help="Marketplace app validation agents: runs the full pipeline for one input folder.",
                  add_completion=False)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def main(
    input_dir: Annotated[Path, typer.Argument(help="inputs/<app> folder: documents + one installer")],
    runs_dir: Annotated[Path | None, typer.Option(help="Where run folders are created (default: CodeBase/runs)")] = None,
    version: Annotated[bool, typer.Option("--version", callback=_show_version, is_eager=True,
                                          help="Print the version and exit")] = False,
) -> None:
    """Run S0 -> S1 -> Agent 1 -> preflight -> Agent 2 -> verdict -> report for INPUT_DIR."""
    raise typer.Exit(code=run(input_dir, runs_dir))


if __name__ == "__main__":
    app()
