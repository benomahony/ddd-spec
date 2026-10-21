import re
import sys
from pathlib import Path

DOCS = Path(__file__).parent.resolve()
REPO = DOCS.parent
CONTENT = DOCS / "content"
LATEST = max((folder.name.removeprefix("v") for folder in (REPO / "spec").glob("v*")), key=lambda version: tuple(map(int, version.split("."))))
SPEC = REPO / "spec" / f"v{LATEST}" / "spec.md"
MODELS = REPO / "tests" / "models" / "invalid"
TITLE = "# ddd-spec"
LANGUAGES = {".py": "python", ".rs": "rust", ".zig": "zig", ".yaml": "yaml", ".yml": "yaml"}


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")


def heading(line: str) -> str:
    hashes, _, title = line.partition(" ")
    assert set(hashes) == {"#"}, f"{line!r} is not a Markdown heading; pass a line beginning with one or more # characters"
    assert slug(title), f"the heading {line!r} has no letters or digits to make an id from; add a word or number"
    return f"{hashes} [{title}]($heading.id('{slug(title)}'))"


def lift(lines: list[str], page: str) -> list[str]:
    body, fenced = [], False
    for line in lines:
        fenced ^= line.startswith("```")
        if not fenced and line.startswith("##"):
            line = heading(line[1:])
        elif not fenced:
            line = re.sub(r"\]\(#([a-z0-9-]+)\)", rf"]($link.page('{page}').ref('\1'))", line)
            line = re.sub(r'!\[(.*?)\]\(docs/assets/(\S+) "(.*?)"\)', r"""[\3](<$image.siteAsset('\2').alt("\1")>)""", line)
        body.append(line)
    return body


def section(lines: list[str], start: str, end: str) -> list[str]:
    first, last = lines.index(start), lines.index(end)
    assert first < last, f"'{end}' comes before '{start}'; keep the sections in order"
    return lines[first + 1 : last]


def page(title: str, description: str, layout: str, body: list[str], order: int) -> str:
    assert '"' not in title + description, f"a quote in {title!r} or {description!r} would end the frontmatter string early"
    assert body, f"no content for {title}"
    front = ["---", f'.title = "{title}",', f'.description = "{description}",', f'.date = .date("2026-10-20T00:00:0{order}"),', f'.layout = "{layout}",', "---", ""]
    return "\n".join(front + body).rstrip() + "\n"


def index() -> str:
    readme = (REPO / "README.md").read_text().splitlines()
    assert readme[0] == TITLE, f"README.md must start with its '{TITLE}' title"
    lede = readme[2]
    assert lede and not lede.startswith(("#", "`", "<")), f"README.md's first paragraph is {lede!r}; start with a sentence saying what ddd-spec is"
    body = section(readme, TITLE, "## Contributing")[3:]
    return page("ddd-spec", lede, "index.shtml", lift(body, "index"), 6)


def specification() -> str:
    text = SPEC.read_text().splitlines()
    assert text[0] == f"# ddd-spec {LATEST}", f"{SPEC} must start with '# ddd-spec {LATEST}'"
    rules = text.index("## Rules")
    linked = [re.sub(r"^\| `([a-z-]+)` \|", r"| [`\1`]($link.page('checks').ref('\1')) |", line) for line in text[rules:]]
    return page(f"Specification {LATEST}", "Every file, field and rule of ddd-spec, normatively.", "structured.shtml", lift(text[1:rules] + linked, "specification"), 3)


def rules() -> list[tuple[str, str, str]]:
    text = SPEC.read_text()
    found = []
    for title, table in re.findall(r"^### (Level [123]: [a-z ]+)\n(.*?)(?=^### |^## )", text[text.index("## Rules") :], re.MULTILINE | re.DOTALL):
        found += [(title, rule, breach) for rule, breach in re.findall(r"^\| `([a-z-]+)` \| (.+?) \|$", table, re.MULTILINE)]
    assert found, f"{SPEC} lists no rules under ## Rules"
    return found


def example(rule: str) -> list[str]:
    root = MODELS / rule
    assert root.is_dir(), f"{rule} has no example model in {MODELS}; add one that breaks it and nothing else"
    lines = []
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        lines += [f"`{path.relative_to(root).as_posix()}`", "", f"```{LANGUAGES.get(path.suffix, '')}", path.read_text().rstrip(), "```", ""]
    return lines


def checks() -> str:
    listed = {rule for _, rule, _ in rules()}
    unlisted = sorted({path.name for path in MODELS.iterdir()} - listed)
    assert not unlisted, f"{MODELS} has models for rules the specification doesn't list: {unlisted}"
    body = [
        "Every rule of the [specification]($link.page('specification').ref('rules')), each with a model that breaks it and nothing else. A tool that implements a rule SHOULD report it for its model, and nothing for the [consistent model](https://github.com/benomahony/ddd-spec/tree/main/tests/models/valid), so the models double as a conformance suite.",
        "",
    ]
    current = None
    for title, rule, breach in rules():
        if title != current:
            body += [heading(f"# {title}"), ""]
            current = title
        body += [f"## [`{rule}`]($heading.id('{rule}'))", "", f"A model breaks it when {breach}.", ""] + example(rule)
    return page("Checks", "Every rule a tool checks, each with a model that breaks it.", "structured.shtml", body, 2)


def examples(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    sources = [REPO / "README.md", *sorted(path for path in CONTENT.glob("*.smd") if path.name != "checks.smd")]
    for source in sources:
        for number, block in enumerate(re.findall(r"```yaml\n(.*?)```", source.read_text(), re.DOTALL)):
            if re.search(r"^(ddd_spec_version|purpose):", block, re.MULTILINE):
                (folder / f"{source.stem}-{number}.yaml").write_text(block)


def main() -> None:
    assert CONTENT.is_dir(), f"{CONTENT} is missing; the site's pages live there"
    for name, text in {"index.smd": index(), "specification.smd": specification(), "checks.smd": checks()}.items():
        (CONTENT / name).write_text(text)
        print(CONTENT / name)
    if sys.argv[1:2] == ["--examples"]:
        examples(Path(sys.argv[2]))


if __name__ == "__main__":
    main()
