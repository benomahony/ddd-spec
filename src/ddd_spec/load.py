import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError

MANIFEST = "ddd.yaml"
FORMAT_PAGE = "https://benomahony.github.io/ddd-spec/format/"
SCHEMA = json.loads(files("ddd_spec").joinpath("ddd.schema.json").read_text())
MANIFEST_VALIDATOR = Draft202012Validator(SCHEMA)
CONTEXT_VALIDATOR = Draft202012Validator({"$ref": "#/$defs/context", "$defs": SCHEMA["$defs"]})


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


@dataclass(frozen=True)
class Context:
    manifest: str
    name: str
    root: Path
    document: Document
    keys: tuple[str, ...]

    @property
    def id(self) -> str:
        return f"{self.manifest}/{self.name}"

    @property
    def data(self) -> CommentedMap:
        node = self.document.data
        for key in self.keys:
            node = node[key]
        return node

    def ref(self, value: str) -> str:
        return value if "/" in value else f"{self.manifest}/{value}"

    def finding(self, check: str, message: str, *keys: str | int) -> Finding:
        return self.document.finding(check, message, *self.keys, *keys)


@dataclass(frozen=True)
class Manifest:
    document: Document
    contexts: list[Context]

    @property
    def id(self) -> str:
        return self.document.data["id"]

    @property
    def root(self) -> Path:
        return self.document.path.parent


def parse(path: Path) -> tuple[CommentedMap | None, list[Finding]]:
    try:
        data = YAML(typ="rt").load(path.read_text())
    except MarkedYAMLError as error:
        mark = error.problem_mark or error.context_mark
        line, column = (mark.line + 1, mark.column + 1) if mark else (1, 1)
        return None, [Finding(path, line, column, "invalid-yaml", f"{error.problem or error.context}; fix the YAML so it parses")]
    if not isinstance(data, CommentedMap):
        return None, [Finding(path, 1, 1, "invalid-document", f"a ddd-spec file is a mapping of fields; see {FORMAT_PAGE}")]
    return data, []


def validate(validator: Draft202012Validator, document: Document) -> list[Finding]:
    findings = []
    for error in sorted(validator.iter_errors(document.data), key=lambda error: list(map(str, error.absolute_path))):
        cause = best_match(error.context) if error.context else error
        findings.append(document.finding("invalid-document", f"{cause.message}; see {FORMAT_PAGE}", *cause.absolute_path))
    return findings


def load(path: Path) -> tuple[Manifest | None, list[Finding]]:
    data, findings = parse(path)
    if data is None:
        return None, findings
    document = Document(path, data)
    findings = validate(MANIFEST_VALIDATOR, document)
    if findings:
        return None, findings
    contexts = []
    for name, entry in data["contexts"].items():
        if isinstance(entry, CommentedMap):
            contexts.append(Context(data["id"], name, path.parent, document, ("contexts", name)))
            continue
        file = path.parent / entry
        if not file.is_file():
            findings.append(document.finding("missing-file", f"{file} doesn't exist; create it, or correct the path", "contexts", name))
            continue
        context_data, problems = parse(file)
        findings += problems
        if context_data is not None:
            context_document = Document(file, context_data)
            problems = validate(CONTEXT_VALIDATOR, context_document)
            findings += problems
            if not problems:
                contexts.append(Context(data["id"], name, path.parent, context_document, ()))
    return Manifest(document, contexts), findings


def manifest_path(path: Path) -> Path:
    return path / MANIFEST if path.is_dir() else path
