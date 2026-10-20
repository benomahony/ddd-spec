import json
from collections.abc import Iterator
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError

FILENAME = "ddd.yaml"
SUFFIX = ".ddd.yaml"
DOCUMENTS_PAGE = "https://benomahony.github.io/ddd-spec/documents/"
VALIDATOR = Draft202012Validator(json.loads(files("ddd_spec").joinpath("ddd.schema.json").read_text()))


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    column: int
    check: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}  error  {self.check}  {self.message}"


@dataclass(frozen=True)
class Document:
    path: Path
    data: CommentedMap

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def kind(self) -> str:
        return self.data["kind"]

    def finding(self, check: str, message: str, *keys: str | int) -> Finding:
        node, line, column = self.data, self.data.lc.line, self.data.lc.col
        for key in keys:
            if isinstance(node, CommentedMap) and key in node:
                line, column = node.lc.key(key)
            elif isinstance(node, CommentedSeq) and isinstance(key, int) and key < len(node):
                line, column = node.lc.item(key)
            else:
                break
            node = node[key]
        return Finding(self.path, line + 1, column + 1, check, message)


def discover(paths: list[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_file():
            yield path
            continue
        for found in sorted(path.rglob("*")):
            hidden = any(part.startswith(".") for part in found.relative_to(path).parts)
            if found.is_file() and not hidden and (found.name == FILENAME or found.name.endswith(SUFFIX)):
                yield found


def load(path: Path) -> tuple[list[Document], list[Finding]]:
    documents, findings = [], []
    try:
        for data in YAML(typ="rt").load_all(path.read_text()):
            if data is None:
                continue
            if not isinstance(data, CommentedMap):
                findings.append(Finding(path, 1, 1, "invalid-document", f"a document is a mapping of fields, not {type(data).__name__}; see {DOCUMENTS_PAGE}"))
                continue
            document = Document(path, data)
            errors = validate(document)
            findings += errors
            if not errors:
                documents.append(document)
    except MarkedYAMLError as error:
        mark = error.problem_mark or error.context_mark
        line, column = (mark.line + 1, mark.column + 1) if mark else (1, 1)
        findings.append(Finding(path, line, column, "invalid-yaml", f"{error.problem or error.context}; fix the YAML so it parses"))
    return documents, findings


def validate(document: Document) -> list[Finding]:
    findings = []
    for error in sorted(VALIDATOR.iter_errors(document.data), key=lambda error: list(map(str, error.absolute_path))):
        cause = best_match(error.context) if error.context else error
        findings.append(document.finding("invalid-document", f"{cause.message}; see {DOCUMENTS_PAGE}", *cause.absolute_path))
    return findings
