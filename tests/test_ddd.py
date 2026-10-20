from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddd_spec.cli import app
from ddd_spec.load import load

TESTS = Path(__file__).parent
runner = CliRunner()


def fixtures(directory: str, pattern: str) -> list[Path]:
    found = sorted((TESTS / directory).glob(pattern))
    assert found, f"no fixtures match {directory}/{pattern}"
    return found


@pytest.mark.parametrize("path", fixtures("valid", "*.yaml"), ids=lambda path: path.stem)
def test_valid_documents_have_no_findings(path: Path) -> None:
    documents, findings = load(path)
    assert findings == []
    assert len(documents) == 1


@pytest.mark.parametrize("path", fixtures("invalid", "*.yaml"), ids=lambda path: path.stem)
def test_invalid_documents_are_rejected(path: Path) -> None:
    documents, findings = load(path)
    assert documents == []
    assert {finding.check for finding in findings} == {"invalid-document"}


def test_a_consistent_model_passes() -> None:
    result = runner.invoke(app, ["check", str(TESTS / "models" / "valid")])
    assert result.exit_code == 0, result.output
    assert "5 documents in 3 files agree" in result.output


@pytest.mark.parametrize("path", fixtures("models/invalid", "*"), ids=lambda path: path.name)
def test_each_invalid_model_fails_only_its_check(path: Path) -> None:
    result = runner.invoke(app, ["check", str(path)])
    checks = {line.split()[2] for line in result.output.splitlines() if "  error  " in line}
    assert result.exit_code == 1, result.output
    assert checks == {path.name}


def test_files_without_a_ddd_name_are_not_searched(tmp_path: Path) -> None:
    (tmp_path / "billing.yaml").write_text("ddd: 0\n")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 2
    assert "no ddd.yaml or *.ddd.yaml files" in result.output


def test_version_names_the_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output == f"ddd {version('ddd-spec')}\n"
