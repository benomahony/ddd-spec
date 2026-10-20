from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddd_spec.cli import app
from ddd_spec.load import CONTEXT_VALIDATOR, MANIFEST_VALIDATOR, Document, parse, validate

TESTS = Path(__file__).parent
MODELS = TESTS / "models"
runner = CliRunner()


def fixtures(directory: Path, pattern: str) -> list[Path]:
    found = sorted(directory.glob(pattern))
    assert found, f"no fixtures match {directory}/{pattern}"
    return found


def schema_findings(path: Path) -> list[str]:
    data, findings = parse(path)
    assert data is not None, findings
    validator = MANIFEST_VALIDATOR if "contexts" in data else CONTEXT_VALIDATOR
    return [finding.check for finding in validate(validator, Document(path, data))]


@pytest.mark.parametrize("path", fixtures(TESTS / "valid", "*.yaml"), ids=lambda path: path.stem)
def test_valid_files_pass_the_schema(path: Path) -> None:
    assert schema_findings(path) == []


@pytest.mark.parametrize("path", fixtures(TESTS / "invalid", "*.yaml"), ids=lambda path: path.stem)
def test_invalid_files_fail_the_schema(path: Path) -> None:
    assert set(schema_findings(path)) == {"invalid-document"}


def test_a_consistent_model_passes() -> None:
    result = runner.invoke(app, ["check", str(MODELS / "valid")])
    assert result.exit_code == 0, result.output
    assert "2 contexts agree with each other and with the code" in result.output


@pytest.mark.parametrize("path", fixtures(MODELS / "invalid", "*"), ids=lambda path: path.name)
def test_each_invalid_model_fails_only_its_check(path: Path) -> None:
    result = runner.invoke(app, ["check", *map(str, fixtures(path, "**/ddd.yaml"))])
    checks = {line.split()[2] for line in result.output.splitlines() if "  error  " in line}
    assert result.exit_code == 1, result.output
    assert checks == {path.name}


def test_a_missing_manifest_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 2
    assert "there is no ddd.yaml" in result.output


def test_explain_prints_the_context_of_a_file() -> None:
    result = runner.invoke(app, ["explain", str(MODELS / "valid" / "src" / "budgeting" / "budget.py")])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("acme.events/budgeting:\n")
    assert "within-allocation:" in result.output


def test_explain_reports_a_file_outside_every_context() -> None:
    result = runner.invoke(app, ["explain", str(MODELS / "valid" / "checks" / "budget_checks.py")])
    assert result.exit_code == 1
    assert "isn't in the code of any context" in result.output


def test_version_names_the_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output == f"ddd {version('ddd-spec')}\n"
