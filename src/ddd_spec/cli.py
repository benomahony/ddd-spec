import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from ruamel.yaml import YAML

from ddd_spec.checks import check_model, check_repository, matched
from ddd_spec.load import MANIFEST, Finding, Manifest, load, manifest_path

app = typer.Typer(add_completion=False)


def show_version(requested: bool) -> None:
    if requested:
        typer.echo(f"ddd {version('ddd-spec')}")
        raise typer.Exit()


@app.callback()
def main(_: Annotated[bool, typer.Option("--version", callback=show_version, is_eager=True, help="Show the version and exit.")] = False) -> None:
    """Validate ddd-spec domain models, and explain them to the people and agents changing the code."""


def count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number or 'no'} {noun}s"


def report(findings: list[Finding]) -> None:
    for finding in sorted(findings, key=lambda finding: (str(finding.path), finding.line, finding.column)):
        typer.echo(str(finding))


def load_all(paths: list[Path]) -> list[Manifest]:
    manifests, findings = [], []
    for path in paths:
        if not manifest_path(path).is_file():
            typer.echo(f"ddd: there is no {MANIFEST} at {manifest_path(path)}; create one, or pass the path of one", err=True)
            raise typer.Exit(2)
        manifest, problems = load(manifest_path(path))
        findings += problems
        if manifest is not None:
            manifests.append(manifest)
    if findings:
        report(findings)
        typer.echo(f"ddd: {count(len(findings), 'problem')} in the files themselves; fix them first")
        raise typer.Exit(1)
    return manifests


@app.command()
def check(paths: Annotated[list[Path] | None, typer.Argument(help=f"Manifests, or directories holding a {MANIFEST}. Pass other repositories' manifests to check references between them.")] = None) -> None:
    """Check the files against the schema, the references between them, and their links to the code."""
    manifests = load_all(paths or [Path(".")])
    model, repository = check_model(manifests), check_repository(manifests)
    report(model + repository)
    contexts = sum(len(manifest.contexts) for manifest in manifests)
    if model or repository:
        typer.echo(f"ddd: {count(len(model), 'problem')} in the model and {count(len(repository), 'problem')} in its links to the code, across {count(contexts, 'context')}")
        raise typer.Exit(1)
    typer.echo(f"ddd: {count(contexts, 'context')} {'agrees' if contexts == 1 else 'agree'} with each other and with the code")


@app.command()
def explain(path: Annotated[Path, typer.Argument(exists=True, help="A file you are about to change.")]) -> None:
    """Print the contexts a file belongs to: their scope, language, invariants and contracts."""
    target = path.resolve()
    manifest_file = next((directory / MANIFEST for directory in target.parents if (directory / MANIFEST).is_file()), None)
    if manifest_file is None:
        typer.echo(f"ddd: no {MANIFEST} in any directory above {path}; create one at the repository root", err=True)
        raise typer.Exit(2)
    manifest = load_all([manifest_file])[0]
    contexts = [context for context in manifest.contexts if any(target in {file.resolve() for file in matched(context.root, pattern)} for pattern in context.data.get("code", []))]
    if not contexts:
        typer.echo(f"ddd: {path} isn't in the code of any context in {manifest_file}; add it to the one it belongs to")
        raise typer.Exit(1)
    yaml = YAML()
    yaml.width = 4096
    yaml.dump({context.id: context.data for context in contexts}, sys.stdout)
