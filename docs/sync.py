import re
from pathlib import Path

DOCS = Path(__file__).parent.resolve()
REPO = DOCS.parent
CONTENT = DOCS / "content"
TITLE = "# ddd.yaml"
PAGES: dict[str, tuple[str, str, str, str, str]] = {
    "index.smd": ("ddd.yaml", "", "index.shtml", TITLE, "## Files"),
    "documents.smd": ("Documents", "Every kind of document, and what each of its fields means.", "page.shtml", "## Files", "## Conformance"),
    "conformance.smd": ("Conformance", "What a tool checks at each level, and how to validate a file.", "page.shtml", "## Conformance", "## Contributing"),
}


def section(readme: list[str], title: str, start: str, end: str) -> list[str]:
    first, last = readme.index(start), readme.index(end)
    assert first < last, f"README.md has '{end}' before '{start}'; keep the sections in order"
    assert last - first > 3, f"README.md's '{start}' section is empty"
    skip = 1 if start.lstrip("# ") == title else 0
    body, fenced = [], False
    for line in readme[first + skip : last]:
        fenced ^= line.startswith("```")
        body.append(heading(line[1:]) if line.startswith("##") and not fenced else line)
    return body


def heading(line: str) -> str:
    hashes, _, title = line.partition(" ")
    slug = re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")
    assert set(hashes) == {"#"}, f"{line!r} is not a Markdown heading; pass a line beginning with one or more # characters"
    assert slug, f"the heading {line!r} has no letters or digits to make an id from; add a word or number"
    return f"{hashes} [{title}]($heading.id('{slug}'))"


def lede(readme: list[str]) -> str:
    paragraph = readme[readme.index(TITLE) + 2]
    assert paragraph and not paragraph.startswith(("#", "`", "<")), f"README.md's first paragraph after its title is {paragraph!r}; start with a sentence saying what ddd.yaml is"
    return paragraph


def page(title: str, description: str, layout: str, body: list[str], order: int) -> str:
    front = ["---", f'.title = "{title}",', f'.description = "{description}",', f'.date = .date("2026-10-20T00:00:0{order}"),', f'.layout = "{layout}",', "---", ""]
    assert '"' not in title + description, f"a quote in {title!r} or {description!r} would end the frontmatter string early"
    assert body, f"no content for {title}"
    return "\n".join(front + body).rstrip() + "\n"


def main() -> None:
    readme = (REPO / "README.md").read_text().splitlines()
    assert TITLE in readme, f"README.md must start with its '{TITLE}' title"
    assert CONTENT.is_dir(), f"{CONTENT} is missing; the site's pages live there"
    description = lede(readme)
    for order, (name, (title, summary, layout, start, end)) in enumerate(PAGES.items()):
        body = [line for line in section(readme, title, start, end) if line != description]
        (CONTENT / name).write_text(page(title, summary or description, layout, body, len(PAGES) - order))
        print(CONTENT / name)


if __name__ == "__main__":
    main()
