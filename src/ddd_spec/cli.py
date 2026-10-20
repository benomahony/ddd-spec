import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from ruamel.yaml import YAML

from ddd_spec.checks import Landscape, check_model, check_repository, consumers, covers
from ddd_spec.load import MANIFEST, Finding, Manifest, load_landscape

app = typer.Typer(add_completion=False)
Remote = Annotated[bool, typer.Option("--remote", help="Fetch imported manifests that are https URLs. Without it, references into them are left unchecked.")]


def show_version(requested: bool) -> None:
    if requested:
        typer.echo(f"ddd-spec {version('ddd-spec')}")
        raise typer.Exit()


@app.callback()
def main(_: Annotated[bool, typer.Option("--version", callback=show_version, is_eager=True, help="Show the version and exit.")] = False) -> None:
    """Validate ddd-spec domain models, and explain them to the people and agents changing the code."""


def count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number or 'no'} {noun}s"


def report(findings: list[Finding]) -> None:
    for finding in sorted(findings, key=lambda finding: (finding.path, finding.line, finding.column)):
        typer.echo(str(finding))


def load_all(paths: list[Path], remote: bool) -> tuple[list[Manifest], list[Manifest]]:
    locations = [str(path / MANIFEST if path.is_dir() else path) for path in paths]
    for location in locations:
        if not Path(location).is_file():
            typer.echo(f"ddd-spec: there is no {MANIFEST} at {location}; create one, or pass the path of one", err=True)
            raise typer.Exit(2)
    primary, everything, findings = load_landscape(locations, remote)
    if findings:
        report(findings)
        typer.echo(f"ddd-spec: {count(len(findings), 'problem')} in the files themselves; fix them first")
        raise typer.Exit(1)
    return primary, everything


@app.command()
def check(paths: Annotated[list[Path] | None, typer.Argument(help=f"Manifests, or directories holding a {MANIFEST}.")] = None, remote: Remote = False) -> None:
    """Check the files against the schema, the references between them, and their links to the code."""
    primary, everything = load_all(paths or [Path(".")], remote)
    model, repository = check_model(everything), check_repository(primary, everything)
    report(model + repository)
    contexts = sum(len(manifest.contexts) for manifest in primary)
    if model or repository:
        typer.echo(f"ddd-spec: {count(len(model), 'problem')} in the model and {count(len(repository), 'problem')} in its links to the code, across {count(contexts, 'context')}")
        raise typer.Exit(1)
    typer.echo(f"ddd-spec: {count(contexts, 'context')} {'agrees' if contexts == 1 else 'agree'} with each other and with the code")


@app.command()
def explain(path: Annotated[Path, typer.Argument(exists=True, help="A file you are about to change.")], remote: Remote = False) -> None:
    """Print the contexts a file belongs to: their scope, language, invariants and contracts, and who uses each contract."""
    target = path.resolve()
    manifest_file = next((directory / MANIFEST for directory in target.parents if (directory / MANIFEST).is_file()), None)
    if manifest_file is None:
        typer.echo(f"ddd-spec: no {MANIFEST} in any directory above {path}; create one at the repository root", err=True)
        raise typer.Exit(2)
    primary, everything = load_all([manifest_file], remote)
    manifest, landscape = primary[0], Landscape(everything)
    name = target.relative_to(manifest_file.parent.resolve()).as_posix()
    owners = [context.id for context in manifest.contexts if covers(context.data.get("code", []), name)]
    owners += [id for id, part in manifest.document.data.get("implements", {}).items() if covers(part["code"], name)]
    if not owners:
        typer.echo(f"ddd-spec: {path} isn't in the code of any context in {manifest_file}; add it to the one it belongs to")
        raise typer.Exit(1)
    explained = {}
    for id in owners:
        context = landscape.contexts.get(id)
        if context is None:
            typer.echo(f"ddd-spec: {id} is defined in a manifest that wasn't loaded; pass --remote to fetch it", err=True)
            explained[id] = None
            continue
        explained[id] = {"context": context.data, "used_by": consumers(context, landscape.contexts)}
    yaml = YAML()
    yaml.width = 4096
    yaml.dump(explained, sys.stdout)
