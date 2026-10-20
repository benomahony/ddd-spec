from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from ddd_spec.checks import check_model
from ddd_spec.load import FILENAME, SUFFIX, discover, load

app = typer.Typer(add_completion=False)


def show_version(requested: bool) -> None:
    if requested:
        typer.echo(f"ddd {version('ddd-spec')}")
        raise typer.Exit()


@app.callback()
def main(_: Annotated[bool, typer.Option("--version", callback=show_version, is_eager=True, help="Show the version and exit.")] = False) -> None:
    """Validate ddd-spec domain models."""


@app.command()
def check(paths: Annotated[list[Path] | None, typer.Argument(exists=True, help=f"Files, or directories to search for {FILENAME} and *{SUFFIX} files.")] = None) -> None:
    """Check each document against the schema, then that the documents agree with each other."""
    searched = paths or [Path(".")]
    found = list(discover(searched))
    if not found:
        typer.echo(f"ddd: no {FILENAME} or *{SUFFIX} files in {', '.join(map(str, searched))}; create one, or pass its path", err=True)
        raise typer.Exit(2)
    documents, findings = [], []
    for path in found:
        loaded, problems = load(path)
        documents += loaded
        findings += problems
    if not findings:
        findings = check_model(documents)
    for finding in sorted(findings, key=lambda finding: (str(finding.path), finding.line, finding.column)):
        typer.echo(str(finding))
    if findings:
        typer.echo(f"ddd: {len(findings)} {'problem' if len(findings) == 1 else 'problems'} in {len(found)} {'file' if len(found) == 1 else 'files'}")
        raise typer.Exit(1)
    typer.echo(f"ddd: {len(documents)} {'document' if len(documents) == 1 else 'documents'} in {len(found)} {'file' if len(found) == 1 else 'files'} agree")
