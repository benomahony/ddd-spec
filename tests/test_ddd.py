import json
import re
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddd_spec.checks import contains, covers, defines, glob, repo_files, words
from ddd_spec.cli import app
from ddd_spec.load import LATEST, Document, parse, validate, validators

TESTS = Path(__file__).parent
REPO = TESTS.parent
MODELS = TESTS / "models"
runner = CliRunner()


def fixtures(directory: Path, pattern: str) -> list[Path]:
    found = sorted(directory.glob(pattern))
    assert found, f"no fixtures match {directory}/{pattern}"
    return found


def schema_findings(path: Path) -> list[str]:
    data, findings = parse(str(path), path.read_text())
    assert data is not None, findings
    manifest, context = validators(LATEST)
    return [finding.check for finding in validate(manifest if "contexts" in data else context, Document(str(path), data))]


def checked(path: Path) -> list[str]:
    return [str(path / "ddd.yaml")] if (path / "ddd.yaml").is_file() else list(map(str, fixtures(path, "*/ddd.yaml")))


@pytest.mark.parametrize("path", fixtures(TESTS / "valid", "*.yaml"), ids=lambda path: path.stem)
def test_valid_files_pass_the_schema(path: Path) -> None:
    assert schema_findings(path) == []


@pytest.mark.parametrize("path", fixtures(TESTS / "invalid", "*.yaml"), ids=lambda path: path.stem)
def test_invalid_files_fail_the_schema(path: Path) -> None:
    assert set(schema_findings(path)) == {"invalid-document"}


def test_a_consistent_model_passes() -> None:
    result = runner.invoke(app, ["check", str(MODELS / "valid")])
    assert result.exit_code == 0, result.output
    assert "5 contexts agree with each other and with the code" in result.output


@pytest.mark.parametrize("path", fixtures(MODELS / "invalid", "*"), ids=lambda path: path.name)
def test_each_invalid_model_fails_only_its_check(path: Path) -> None:
    result = runner.invoke(app, ["check", *checked(path)])
    found = {line.split()[2] for line in result.output.splitlines() if "  error  " in line}
    assert result.exit_code == 1, result.output
    assert found == {path.name}


def test_a_manifest_passed_twice_is_loaded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(MODELS / "valid")
    result = runner.invoke(app, ["check", ".", "./ddd.yaml", str(MODELS / "valid")])
    assert result.exit_code == 0, result.output
    assert "5 contexts agree" in result.output


def test_a_file_without_a_document_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "ddd.yaml").write_text("# just a comment\n---\n")
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 1
    assert "invalid-document  a ddd-spec file is a mapping of fields" in result.output


@pytest.mark.parametrize("text", ["a: &x 1\nb: *x\n", "a: !custom 1\n", "a: !!str 1\n"], ids=["anchor", "custom-tag", "core-tag"])
def test_anchors_aliases_and_tags_are_refused(text: str) -> None:
    data, findings = parse("ddd.yaml", text)
    assert data is None
    assert [finding.check for finding in findings] == ["invalid-yaml"]


def test_a_missing_manifest_is_a_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path)])
    assert result.exit_code == 2
    assert "there is no ddd.yaml" in result.output


def test_explain_prints_a_files_context_and_who_uses_its_contracts() -> None:
    result = runner.invoke(app, ["explain", str(MODELS / "valid" / "src" / "budgeting" / "budget.py")])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("acme.events/budgeting:\n  context:\n")
    assert "within-allocation:" in result.output
    assert "used_by: {}" in result.output


def test_explain_follows_implements_into_an_imported_manifest() -> None:
    result = runner.invoke(app, ["explain", str(MODELS / "valid" / "src" / "postings" / "poster.py")])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("acme.ledger/postings:\n")
    assert "    - context: acme.events/budgeting\n      model: translate\n" in result.output


def test_explain_reports_a_file_outside_every_context() -> None:
    result = runner.invoke(app, ["explain", str(MODELS / "valid" / "checks" / "budget_checks.py")])
    assert result.exit_code == 1
    assert "isn't in the code of any context" in result.output


@pytest.fixture
def served() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(MODELS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_remote_imports_are_checked_only_when_fetched(tmp_path: Path, served: str) -> None:
    (tmp_path / "ddd.yaml").write_text(f"""ddd_spec_version: "0.1"
id: acme.events
imports:
  acme.ledger: {served}/ledger/ddd.yaml
contexts:
  budgeting:
    purpose: Control the full committed cost of an event.
    uses:
      acme.ledger/postingz: {{ model: translate, contracts: [PostingRecorded] }}
""")
    offline = runner.invoke(app, ["check", str(tmp_path)])
    fetched = runner.invoke(app, ["check", "--remote", str(tmp_path)])
    assert offline.exit_code == 0, offline.output
    assert fetched.exit_code == 1, fetched.output
    assert "unknown-context  acme.ledger has no context called 'postingz'" in fetched.output


@pytest.mark.parametrize(
    ("pattern", "name", "expected"),
    [
        ("src/**", "src/a/b.py", True),
        ("src/**", "src", False),
        ("src/*.py", "src/a/b.py", False),
        ("src/**/*.py", "src/b.py", True),
        ("**/test_*.py", "a/b/test_c.py", True),
        ("src/?.py", "src/ab.py", False),
        ("Src/**", "src/a.py", False),
    ],
)
def test_globs_follow_the_spec(pattern: str, name: str, expected: bool) -> None:
    assert bool(glob(pattern).fullmatch(name)) is expected


@pytest.mark.parametrize(
    ("text", "symbol", "expected"),
    [
        ("class Budget:\n    def reserve(self, amount):\n", "Budget.reserve", True),
        ("impl Budget {\n    pub fn reserve(&mut self) -> bool {\n", "Budget::reserve", True),
        ("public class Budget {\n  public void reserve(int amount) {\n", "Budget#reserve", True),
        ("func (b *Budget) Reserve(amount int) error {\n", "Budget.Reserve", True),
        ("class Budget {\n  reserve(amount: number): void {\n", "Budget.reserve", True),
        ("const reserve = (amount) => amount;\n", "reserve", True),
        ("# Budget.reserve keeps commitments in bounds\n", "Budget.reserve", False),
        ("budget = Budget()\nbudget.reserve(5)\n", "Budget.reserve", False),
        ('test "a fix is written only over its bytes" {\n', '"a fix is written only over its bytes"', True),
        ('// test "a fix is written only over its bytes"\n', '"a fix is written only over its bytes"', False),
    ],
)
def test_symbols_must_be_defined_not_only_mentioned(text: str, symbol: str, expected: bool) -> None:
    assert defines(text, symbol) is expected


@pytest.mark.parametrize(
    ("patterns", "name", "expected"),
    [
        (["src/**", "!src/infer.zig"], "src/infer.zig", False),
        (["src/**", "!src/infer.zig"], "src/check.zig", True),
        (["src/**", "!src/*.zig", "src/main.zig"], "src/main.zig", True),
        (["!src/**"], "src/main.zig", False),
    ],
)
def test_a_negated_glob_takes_back_what_came_before_it(patterns: list[str], name: str, expected: bool) -> None:
    assert covers(patterns, name) is expected


def test_globs_skip_hidden_directories_but_not_dotfiles(tmp_path: Path) -> None:
    for name in (".github/workflows/ci.yml", ".pre-commit-hooks.yaml", "src/a.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")
    assert repo_files(tmp_path) == (".pre-commit-hooks.yaml", "src/a.py")


def test_identifiers_split_into_words() -> None:
    assert words("costCentreID_v2") == ["cost", "centre", "id", "v", "2"]
    assert words("HTTPServer") == ["http", "server"]


@pytest.mark.parametrize(
    ("identifier", "found"),
    [("costCentreId", True), ("COST_CENTRE", True), ("costCentres", True), ("cost_of_centre", False), ("centre_cost", False), ("costCentrez", False)],
)
def test_the_specs_example_of_an_avoided_word(identifier: str, found: bool) -> None:
    assert contains(words(identifier), words("cost centre")) is found


@pytest.mark.parametrize(("identifier", "found"), [("self.holds", True), ("holdes", True), ("holder", False), ("holdings", False), ("user", False)])
def test_an_avoided_word_matches_its_plural_but_not_longer_words(identifier: str, found: bool) -> None:
    assert any(contains(words(part), words("hold")) for part in identifier.split(".")) is found


def test_every_rule_in_the_spec_has_a_failing_model_and_no_other_does() -> None:
    text = (REPO / "spec" / f"v{LATEST}" / "spec.md").read_text()
    rules = set(re.findall(r"^\| `([a-z-]+)` \|", text[text.index("## Rules") :], re.MULTILINE))
    assert len(rules) > 20
    assert rules == {path.name for path in fixtures(MODELS / "invalid", "*")}


def test_each_schema_names_its_own_version() -> None:
    for folder in fixtures(REPO / "spec", "v*"):
        schema = json.loads((folder / "ddd.schema.json").read_text())
        assert schema["$id"] == f"https://benomahony.github.io/ddd-spec/{folder.name}/ddd.schema.json"
        assert schema["$defs"]["manifest"]["properties"]["ddd_spec_version"]["const"] == folder.name.removeprefix("v")


def test_the_readme_describes_the_latest_version() -> None:
    readme = (REPO / "README.md").read_text()
    assert set(re.findall(r'ddd_spec_version: "([0-9.]+)"', readme)) == {LATEST}
    assert set(re.findall(r"ddd-spec/v([0-9.]+)/ddd\.schema\.json", readme)) == {LATEST}


def documented_files() -> list[tuple[str, str]]:
    sources = [REPO / "README.md", *sorted(path for path in (REPO / "docs" / "content").glob("*.smd") if path.name != "checks.smd")]
    blocks = [(f"{source.name}:{index}", block) for source in sources for index, block in enumerate(re.findall(r"```yaml\n(.*?)```", source.read_text(), re.DOTALL))]
    return [(name, block) for name, block in blocks if re.search(r"^(ddd_spec_version|purpose):", block, re.MULTILINE)]


@pytest.mark.parametrize(("name", "block"), documented_files(), ids=lambda value: value if ":" in value and "\n" not in value else "")
def test_every_whole_file_the_docs_show_is_valid(name: str, block: str) -> None:
    data, findings = parse(name, block)
    assert data is not None, findings
    manifest, context = validators(LATEST)
    assert validate(manifest if "contexts" in data else context, Document(name, data)) == []


def test_version_names_the_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output == f"ddd-spec {version('ddd-spec')}\n"
