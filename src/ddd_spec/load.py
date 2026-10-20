import json
import os
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import urlopen

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import MarkedYAMLError

MANIFEST = "ddd.yaml"
FORMAT_PAGE = "https://benomahony.github.io/ddd-spec/format/"
SCHEMAS = {folder.name.removeprefix("v"): json.loads(folder.joinpath("ddd.schema.json").read_text()) for folder in files("ddd_spec").joinpath("schema").iterdir()}
LATEST = max(SCHEMAS, key=lambda version: tuple(map(int, version.split("."))))


@cache
def validators(version: str) -> tuple[Draft202012Validator, Draft202012Validator]:
    schema = SCHEMAS.get(version, SCHEMAS[LATEST])
    checker = Draft202012Validator.FORMAT_CHECKER
    context = {"$ref": "#/$defs/context", "$defs": schema["$defs"]}
    return Draft202012Validator(schema, format_checker=checker), Draft202012Validator(context, format_checker=checker)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    check: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}  error  {self.check}  {self.message}"


@dataclass(frozen=True)
class Document:
    path: str
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
    root: Path | None
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
    root: Path | None
    imported: dict[str, str | None] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.document.data["id"]

    @property
    def location(self) -> str:
        return self.document.path

    def declares(self, manifest_id: str) -> bool:
        return manifest_id == self.id or manifest_id in self.document.data.get("imports", {})


def is_url(location: str) -> bool:
    return location.startswith(("https://", "http://"))


def resolve(base: str, relative: str) -> str:
    if is_url(relative):
        return relative
    if is_url(base):
        return urljoin(base, relative)
    return os.path.normpath(Path(base).parent / relative)


def read(location: str) -> str | None:
    if is_url(location):
        try:
            with urlopen(location, timeout=20) as response:
                return response.read().decode()
        except (URLError, TimeoutError, UnicodeDecodeError):
            return None
    path = Path(location)
    return path.read_text() if path.is_file() else None


def parse(location: str, text: str) -> tuple[CommentedMap | None, list[Finding]]:
    try:
        data = YAML(typ="rt").load(text)
    except MarkedYAMLError as error:
        mark = error.problem_mark or error.context_mark
        line, column = (mark.line + 1, mark.column + 1) if mark else (1, 1)
        return None, [Finding(location, line, column, "invalid-yaml", f"{error.problem or error.context}; fix the YAML so it parses")]
    if not isinstance(data, CommentedMap):
        return None, [Finding(location, 1, 1, "invalid-document", f"a ddd-spec file is a mapping of fields; see {FORMAT_PAGE}")]
    return data, []


def validate(validator: Draft202012Validator, document: Document) -> list[Finding]:
    findings = []
    for error in sorted(validator.iter_errors(document.data), key=lambda error: list(map(str, error.absolute_path))):
        cause = best_match(error.context) if error.context else error
        findings.append(document.finding("invalid-document", f"{cause.message}; see {FORMAT_PAGE}", *cause.absolute_path))
    return findings


def load(location: str, text: str) -> tuple[Manifest | None, list[Finding]]:
    data, findings = parse(location, text)
    if data is None:
        return None, findings
    document = Document(location, data)
    manifest_validator, context_validator = validators(str(data.get("ddd_spec_version", LATEST)))
    findings = validate(manifest_validator, document)
    if findings:
        return None, findings
    root = None if is_url(location) else Path(location).parent
    contexts = []
    for name, entry in data["contexts"].items():
        if isinstance(entry, CommentedMap):
            contexts.append(Context(data["id"], name, root, document, ("contexts", name)))
            continue
        file = resolve(location, entry)
        text = read(file)
        if text is None:
            findings.append(document.finding("missing-file", f"{file} can't be read; create it, or correct the path", "contexts", name))
            continue
        context_data, problems = parse(file, text)
        findings += problems
        if context_data is not None:
            context_document = Document(file, context_data)
            problems = validate(context_validator, context_document)
            findings += problems
            if not problems:
                contexts.append(Context(data["id"], name, root, context_document, ()))
    return Manifest(document, contexts, root), findings


def load_landscape(locations: list[str], remote: bool) -> tuple[list[Manifest], list[Manifest], list[Finding]]:
    primary, everything, findings = [], [], []
    loaded: dict[str, Manifest] = {}
    queue = [(location, None, None) for location in locations]
    while queue:
        location, importer, key = queue.pop(0)
        if location in loaded or (is_url(location) and not remote):
            if importer is not None:
                importer.imported[key] = loaded[location].id if location in loaded else None
            continue
        text = read(location)
        if text is None:
            if importer is None:
                findings.append(Finding(location, 1, 1, "missing-file", f"{location} can't be read; create it, or correct the path"))
            else:
                findings.append(importer.document.finding("missing-file", f"{location} can't be read; correct the import, or pass --remote to fetch URLs", "imports", key))
            continue
        manifest, problems = load(location, text)
        findings += problems
        if manifest is None:
            continue
        loaded[location] = manifest
        everything.append(manifest)
        if importer is None:
            primary.append(manifest)
        else:
            importer.imported[key] = manifest.id
        for name, target in manifest.document.data.get("imports", {}).items():
            queue.append((resolve(location, target), manifest, name))
    return primary, everything, findings
