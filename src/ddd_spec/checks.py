import re
import subprocess
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from ddd_spec.load import Context, Finding, Manifest

COMMENT = ("#", "//", "/*", "*", "--", ";")
DEFINITION = r"\b(?:class|struct|enum|trait|interface|type|record|object|module|impl|def|fn|func|fun|function|sub|proc|const|let|var|val|static)\s+(?:\([^)]*\)\s*)?"
SIGNATURE = r"\s*\([^;{}]*\)\s*(?:\{|=>|throws\b|:|->)"
ASSIGNED = r"\s*[:=]\s*(?:\(|function\b|async\b|lambda\b)"


class Landscape:
    def __init__(self, manifests: list[Manifest]) -> None:
        self.manifests = {manifest.id: manifest for manifest in reversed(manifests)}
        self.contexts = {context.id: context for manifest in manifests for context in manifest.contexts}

    def lookup(self, context: Context, reference: str, *keys: str | int) -> tuple[Context | None, list[Finding]]:
        target = context.ref(reference)
        manifest_id = target.partition("/")[0]
        if not self.manifests[context.manifest].declares(manifest_id):
            return None, [context.finding("unknown-manifest", f"{context.manifest} doesn't import a manifest called '{manifest_id}'; add it to imports, or correct the id", *keys)]
        if manifest_id not in self.manifests:
            return None, []
        if target not in self.contexts:
            return None, [context.finding("unknown-context", f"{manifest_id} has no context called '{target.partition('/')[2]}'; check the spelling, or add it to that manifest", *keys)]
        return self.contexts[target], []


def deprecated(context: Context, what: str, *keys: str | int) -> Finding:
    return context.finding("deprecated-reference", f"{what} is deprecated; move to what replaces it", *keys)


def check_model(manifests: list[Manifest]) -> list[Finding]:
    landscape = Landscape(manifests)
    findings = duplicate_ids(manifests) + imports(manifests) + implements(manifests, landscape)
    for context in landscape.contexts.values():
        findings += references(context, landscape) + aggregates(context) + policies(context, landscape) + agreements(context, landscape) + invariants(context)
    return findings + cycles(landscape.contexts)


def duplicate_ids(manifests: list[Manifest]) -> list[Finding]:
    seen: dict[str, Manifest] = {}
    findings = []
    for manifest in manifests:
        if manifest.id in seen:
            findings.append(manifest.document.finding("duplicate-id", f"'{manifest.id}' is already the id of {seen[manifest.id].location}; give each manifest its own id", "id"))
        seen.setdefault(manifest.id, manifest)
    return findings


def imports(manifests: list[Manifest]) -> list[Finding]:
    findings = []
    for manifest in manifests:
        for key, loaded in manifest.imported.items():
            if loaded is not None and loaded != key:
                findings.append(manifest.document.finding("import-mismatch", f"the manifest imported as '{key}' has the id '{loaded}'; import it under its own id", "imports", key))
    return findings


def implements(manifests: list[Manifest], landscape: Landscape) -> list[Finding]:
    findings = []
    for manifest in manifests:
        for target in manifest.document.data.get("implements", {}):
            manifest_id = target.partition("/")[0]
            if not manifest.declares(manifest_id):
                findings.append(manifest.document.finding("unknown-manifest", f"{manifest.id} doesn't import a manifest called '{manifest_id}'; add it to imports, or correct the id", "implements", target))
            elif manifest_id in landscape.manifests and target not in landscape.contexts:
                findings.append(manifest.document.finding("unknown-context", f"{manifest_id} has no context called '{target.partition('/')[2]}'; check the spelling, or add it to that manifest", "implements", target))
    return findings


def references(context: Context, landscape: Landscape) -> list[Finding]:
    findings = []
    for field in ("customers", "partners"):
        for index, reference in enumerate(context.data.get(field, [])):
            customer, problems = landscape.lookup(context, reference, field, index)
            findings += problems
            if field == "customers" and customer is not None and context.id not in map(customer.ref, customer.data.get("uses", {})):
                findings.append(context.finding("customer-without-use", f"{customer.id} doesn't use any contract of {context.id}; remove it from customers, or record what it uses", field, index))
    for term, entry in context.data.get("language", {}).items():
        if not isinstance(entry, dict) or "from" not in entry:
            continue
        reference, _, name = entry["from"].partition("#")
        source, problems = landscape.lookup(context, reference, "language", term, "from")
        findings += problems
        if source is None:
            continue
        theirs = source.data.get("language", {}).get(name)
        if theirs is None:
            findings.append(context.finding("unknown-term", f"'{name}' is not a term in {source.id}'s language; add it there, or translate from a term it defines", "language", term, "from"))
        elif isinstance(theirs, dict) and theirs.get("status") == "deprecated":
            findings.append(deprecated(context, f"{source.id}'s term '{name}'", "language", term, "from"))
    for reference, use in context.data.get("uses", {}).items():
        provider, problems = landscape.lookup(context, reference, "uses", reference)
        findings += problems
        if provider is None:
            continue
        if provider.data.get("status") == "deprecated":
            findings.append(deprecated(context, provider.id, "uses", reference))
        provided = provider.data.get("provides", {})
        for index, pinned in enumerate(use.get("contracts", [])):
            name, _, wanted = pinned.partition("@")
            contract = provided.get(name)
            if contract is None:
                findings.append(context.finding("unknown-contract", f"{provider.id} doesn't provide {name}; add it to its provides, or correct the name", "uses", reference, "contracts", index))
            elif contract.get("status") == "deprecated":
                findings.append(deprecated(context, f"{provider.id}'s {name}", "uses", reference, "contracts", index))
            elif not contract.get("published") and use["model"] != "share" and not (lists(context, provider, "partners") and lists(provider, context, "partners")):
                findings.append(context.finding("unpublished-contract", f"{provider.id} hasn't published {name}, so it can change without warning; ask its owner to publish it, or share a kernel instead", "uses", reference, "contracts", index))
            elif wanted and contract.get("version") != wanted:
                current = f"is at version {contract['version']}" if "version" in contract else "has no version"
                findings.append(context.finding("outdated-contract", f"{context.id} was built against {name}@{wanted}, but {provider.id}'s {name} {current}; update this context and its pin", "uses", reference, "contracts", index))
        domain = context.data.get("classification", {}).get("domain")
        theirs = provider.data.get("classification", {}).get("domain")
        if use["model"] == "conform" and domain == "core" and theirs is not None and theirs != "core":
            findings.append(context.finding("core-conforms", f"{context.id} is core but conforms to {provider.id}, which is {theirs}; translate its model into this one's instead", "uses", reference, "model"))
    return findings


def contract(context: Context, reference: str, landscape: Landscape, *keys: str | int) -> tuple[Context | None, dict | None, list[Finding]]:
    owner_ref, _, name = reference.rpartition("#")
    owner, problems = landscape.lookup(context, owner_ref, *keys) if owner_ref else (context, [])
    if owner is None:
        return None, None, problems
    provided = owner.data.get("provides", {}).get(name)
    if provided is None:
        return owner, None, [context.finding("unknown-contract", f"{owner.id} doesn't provide {name}; add it to its provides, or correct the name", *keys)]
    return owner, provided, []


def policies(context: Context, landscape: Landscape) -> list[Finding]:
    findings = []
    used = {context.ref(reference): {pinned.partition("@")[0] for pinned in use.get("contracts", [])} for reference, use in context.data.get("uses", {}).items()}
    for name, policy in context.data.get("policies", {}).items():
        steps = [("when", policy["when"], "event", ("policies", name, "when"))]
        steps += [("then", reference, "command", ("policies", name, "then", index)) for index, reference in enumerate(policy["then"])]
        for field, reference, kind, keys in steps:
            owner, provided, problems = contract(context, reference, landscape, *keys)
            findings += problems
            if provided is None:
                continue
            contract_name = reference.rpartition("#")[2]
            if provided["kind"] != kind:
                findings.append(context.finding("wrong-contract-kind", f"{contract_name} is {article(provided['kind'])}, but a policy's {field} names {article(kind)}; correct its kind, or name another contract", *keys))
            elif owner.id != context.id and contract_name not in used.get(owner.id, set()):
                findings.append(context.finding("undeclared-use", f"the policy relies on {owner.id}'s {contract_name}, but {context.id} doesn't list it in uses; add it there", *keys))
    return findings


def aggregates(context: Context) -> list[Finding]:
    findings = []
    provided = context.data.get("provides", {})
    for name, aggregate in context.data.get("aggregates", {}).items():
        for field, kind in (("handles", "command"), ("emits", "event")):
            for index, contract in enumerate(aggregate.get(field, [])):
                if contract not in provided:
                    findings.append(context.finding("unknown-contract", f"{context.id} doesn't provide {contract}; add it to provides, or correct the name", "aggregates", name, field, index))
                elif provided[contract]["kind"] != kind:
                    findings.append(context.finding("wrong-contract-kind", f"{contract} is {article(provided[contract]['kind'])}, but an aggregate only {field} {article(kind)}; correct its kind, or move it", "aggregates", name, field, index))
    return findings


def article(noun: str) -> str:
    return f"an {noun}" if noun[0] in "aeiou" else f"a {noun}"


def shares(a: Context, b: Context) -> bool:
    return any(a.ref(reference) == b.id and use["model"] == "share" for reference, use in a.data.get("uses", {}).items())


def lists(a: Context, b: Context, field: str) -> bool:
    return b.id in map(a.ref, a.data.get(field, []))


def agreements(context: Context, landscape: Landscape) -> list[Finding]:
    findings = []
    for index, reference in enumerate(context.data.get("partners", [])):
        other = landscape.contexts.get(context.ref(reference))
        if other is not None and not lists(other, context, "partners"):
            findings.append(context.finding("one-sided-partnership", f"{other.id} doesn't list {context.id} as a partner; a partnership needs both sides, so add it there or remove it here", "partners", index))
    for reference, use in context.data.get("uses", {}).items():
        other = landscape.contexts.get(context.ref(reference))
        if use["model"] == "share" and other is not None and not shares(other, context):
            findings.append(context.finding("one-sided-shared-kernel", f"{other.id} doesn't share a kernel with {context.id}; add a use with model share there, or translate here", "uses", reference, "model"))
    return findings


def invariants(context: Context) -> list[Finding]:
    findings = []
    known = context.data.get("aggregates", {})
    for name, invariant in context.data.get("invariants", {}).items():
        for index, aggregate in enumerate(invariant.get("applies_to", [])):
            if aggregate not in known:
                findings.append(context.finding("unknown-aggregate", f"{context.id} has no aggregate called '{aggregate}'; add it to aggregates, or correct the name", "invariants", name, "applies_to", index))
        if invariant["status"] == "implemented" and not invariant.get("enforced_by") and not invariant.get("verified_by"):
            findings.append(context.finding("implemented-without-evidence", "the invariant is marked implemented but names no code that enforces it and no test that verifies it; add enforced_by or verified_by, or mark it proposed", "invariants", name, "status"))
    return findings


def cycles(contexts: dict[str, Context]) -> list[Finding]:
    edges = {id: {context.ref(reference) for reference in context.data.get("uses", {})} & contexts.keys() for id, context in contexts.items()}
    findings = []
    for component in strongly_connected(edges):
        loose = [(a, b) for a in component for b in edges[a] & component if not coupled(contexts[a], contexts[b])]
        if loose:
            first, second = min(loose)
            context = contexts[first]
            reference = next(reference for reference in context.data["uses"] if context.ref(reference) == second)
            findings.append(context.finding("dependency-cycle", f"{', '.join(sorted(component))} depend on each other through uses; break the cycle, or make them partners", "uses", reference))
    return findings


def coupled(a: Context, b: Context) -> bool:
    return (lists(a, b, "partners") and lists(b, a, "partners")) or shares(a, b)


def strongly_connected(edges: dict[str, set[str]]) -> Iterator[set[str]]:
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    for start in sorted(edges):
        if start in index:
            continue
        work = [(start, iter(sorted(edges[start])))]
        index[start] = low[start] = len(index)
        stack.append(start)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is None:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component = set()
                    while (member := stack.pop()) != node:
                        component.add(member)
                    component.add(node)
                    if len(component) > 1:
                        yield component
            elif child not in index:
                index[child] = low[child] = len(index)
                stack.append(child)
                work.append((child, iter(sorted(edges[child]))))
            elif child in stack:
                low[node] = min(low[node], index[child])


def consumers(context: Context, contexts: dict[str, Context]) -> dict[str, list[dict[str, str]]]:
    used: dict[str, list[dict[str, str]]] = {}
    for other in contexts.values():
        for reference, use in other.data.get("uses", {}).items():
            if other.ref(reference) == context.id:
                for pinned in use.get("contracts", []):
                    name, _, version = pinned.partition("@")
                    used.setdefault(name, []).append({"context": other.id, "model": use["model"]} | ({"built_against": version} if version else {}))
    return used


@cache
def repo_files(root: Path) -> tuple[str, ...]:
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, check=True).stdout.decode().split("\0")
    except (OSError, subprocess.CalledProcessError):
        listed = [path.relative_to(root).as_posix() for path in root.rglob("*")]
    return tuple(sorted(name for name in listed if name and not any(part.startswith(".") for part in name.split("/")[:-1]) and (root / name).is_file()))


@cache
def glob(pattern: str) -> re.Pattern[str]:
    parts, index = [], 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        else:
            parts.append({"*": "[^/]*", "?": "[^/]"}.get(pattern[index], re.escape(pattern[index])))
            index += 1
    return re.compile("".join(parts))


def matched(root: Path, pattern: str) -> list[str]:
    return [name for name in repo_files(root) if glob(pattern.removeprefix("!")).fullmatch(name)]


def covers(patterns: list[str], name: str) -> bool:
    included = False
    for pattern in patterns:
        if glob(pattern.removeprefix("!")).fullmatch(name):
            included = not pattern.startswith("!")
    return included


def claimed(root: Path, patterns: list[str]) -> list[str]:
    return [name for name in repo_files(root) if covers(patterns, name)]


def code_refs(context: Context) -> Iterator[tuple[str, tuple[str | int, ...]]]:
    for term, entry in context.data.get("language", {}).items():
        if isinstance(entry, dict):
            for index, reference in enumerate(entry.get("code", [])):
                yield reference, ("language", term, "code", index)
    for name, aggregate in context.data.get("aggregates", {}).items():
        if "root" in aggregate:
            yield aggregate["root"], ("aggregates", name, "root")
    for name, invariant in context.data.get("invariants", {}).items():
        for field in ("enforced_by", "verified_by"):
            for index, reference in enumerate(invariant.get(field, [])):
                yield reference, ("invariants", name, field, index)


def defines(text: str, symbol: str) -> bool:
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(COMMENT))
    if symbol.startswith('"'):
        return symbol in code
    parts = [part for part in re.split(r"\.|::|#|/", symbol) if part]
    if not all(re.search(rf"\b{re.escape(part)}\b", code) for part in parts):
        return False
    name = re.escape(parts[-1])
    return any(re.search(pattern, code) for pattern in (DEFINITION + name + r"\b", r"\b" + name + SIGNATURE, r"\b" + name + ASSIGNED))


def check_repository(manifests: list[Manifest], landscape_manifests: list[Manifest]) -> list[Finding]:
    landscape = Landscape(landscape_manifests)
    findings = []
    for manifest in manifests:
        if manifest.root is None:
            continue
        claims: dict[str, list[Context | str]] = {}
        for context in manifest.contexts:
            patterns = context.data.get("code", [])
            for index, pattern in enumerate(patterns):
                if not matched(context.root, pattern):
                    findings.append(context.finding("missing-path", f"no file in {context.root} matches {pattern}; correct the glob, or remove it", "code", index))
            for name in claimed(context.root, patterns):
                claims.setdefault(name, []).append(context)
            for reference, keys in code_refs(context):
                findings += symbol(context, reference, keys)
            for reference, use in context.data.get("uses", {}).items():
                for index, pattern in enumerate(use.get("code", [])):
                    if not matched(context.root, pattern):
                        findings.append(context.finding("missing-path", f"no file in {context.root} matches {pattern}; correct the glob, or remove it", "uses", reference, "code", index))
            findings += avoided_words(context, context.root, context.data.get("code", []))
        for target, part in manifest.document.data.get("implements", {}).items():
            for index, pattern in enumerate(part["code"]):
                if not matched(manifest.root, pattern):
                    findings.append(manifest.document.finding("missing-path", f"no file in {manifest.root} matches {pattern}; correct the glob, or remove it", "implements", target, "code", index))
            for name in claimed(manifest.root, part["code"]):
                claims.setdefault(name, []).append(target)
            if target in landscape.contexts:
                findings += avoided_words(landscape.contexts[target], manifest.root, part["code"])
        for name, claimants in sorted(claims.items()):
            unique = list({claimant.id if isinstance(claimant, Context) else claimant: claimant for claimant in claimants}.values())
            if len(unique) > 1 and not kernel(unique, name, landscape):
                ids = [claimant.id if isinstance(claimant, Context) else claimant for claimant in unique]
                last = unique[-1]
                where = last.finding if isinstance(last, Context) else lambda check, message: manifest.document.finding(check, message, "implements", last)
                findings.append(where("overlapping-code", f"{name} is in the code of {' and '.join(ids)}, but not in a kernel they share; give it to one context, or add it to their shared kernel's code"))
    return findings


def shared_code(a: Context, b: Context, name: str) -> bool:
    return any(a.ref(reference) == b.id and use["model"] == "share" and covers(use["code"], name) for reference, use in a.data.get("uses", {}).items())


def kernel(claimants: list[Context | str], name: str, landscape: Landscape) -> bool:
    contexts = [claimant if isinstance(claimant, Context) else landscape.contexts.get(claimant) for claimant in claimants]
    return all(a is not None and b is not None and (shared_code(a, b, name) or shared_code(b, a, name)) for a in contexts for b in contexts if a is not b)


def symbol(context: Context, reference: str, keys: tuple[str | int, ...]) -> list[Finding]:
    file, _, name = reference.partition("#")
    path = context.root / file
    if not path.is_file():
        return [context.finding("missing-path", f"{file} doesn't exist in {context.root}; correct the path, or remove it", *keys)]
    if name and not defines(path.read_text(errors="replace"), name):
        return [context.finding("missing-symbol", f"{file} doesn't define {name}; correct the symbol, or point at the file that defines it", *keys)]
    return []


def words(identifier: str) -> list[str]:
    return [word.lower() for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+", identifier)]


def contains(found: list[str], phrase: list[str]) -> bool:
    endings = {phrase[-1], phrase[-1] + "s", phrase[-1] + "es"}
    return any(found[start : start + len(phrase) - 1] == phrase[:-1] and found[start + len(phrase) - 1] in endings for start in range(len(found) - len(phrase) + 1))


def avoided_words(context: Context, root: Path | None, patterns: list[str]) -> list[Finding]:
    avoided = [(entry.get("term", term.replace("-", " ")), word, words(word)) for term, entry in context.data.get("language", {}).items() if isinstance(entry, dict) for word in entry.get("not", [])]
    if not avoided or root is None:
        return []
    findings = []
    for name in claimed(root, patterns):
        path = root / name
        text = path.read_text(errors="replace")
        if "\0" in text:
            continue
        reported = set()
        for number, line in enumerate(text.splitlines(), 1):
            for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", line):
                found = words(match.group())
                for term, word, phrase in avoided:
                    if word not in reported and contains(found, phrase):
                        reported.add(word)
                        findings.append(Finding(str(path), number, match.start() + 1, "avoided-word", f"'{word}' stands in for '{term}' in {context.id}; say {term}"))
    return findings
