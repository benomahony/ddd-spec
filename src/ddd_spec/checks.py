import re
from collections.abc import Iterator
from pathlib import Path

from ddd_spec.load import Context, Finding, Manifest


def contexts_of(manifests: list[Manifest]) -> dict[str, Context]:
    return {context.id: context for manifest in manifests for context in manifest.contexts}


def known(reference: str, manifests: list[Manifest]) -> bool:
    return reference.partition("/")[0] in {manifest.id for manifest in manifests}


def check_model(manifests: list[Manifest]) -> list[Finding]:
    findings = duplicate_ids(manifests)
    contexts = contexts_of(manifests)
    for context in contexts.values():
        findings += references(context, contexts, manifests) + agreements(context, contexts) + invariants(context)
    return findings + cycles(contexts)


def duplicate_ids(manifests: list[Manifest]) -> list[Finding]:
    seen: dict[str, Manifest] = {}
    findings = []
    for manifest in manifests:
        if manifest.id in seen:
            findings.append(manifest.document.finding("duplicate-id", f"'{manifest.id}' is already the id of {seen[manifest.id].document.path}; give each manifest its own id", "id"))
        seen.setdefault(manifest.id, manifest)
    return findings


def unknown_context(context: Context, reference: str, *keys: str | int) -> Finding:
    return context.finding("unknown-context", f"{context.ref(reference).partition('/')[0]} has no context called '{context.ref(reference).partition('/')[2]}'; check the spelling, or add it to that manifest", *keys)


def references(context: Context, contexts: dict[str, Context], manifests: list[Manifest]) -> list[Finding]:
    findings = []
    for field in ("customers", "partners"):
        for index, reference in enumerate(context.data.get(field, [])):
            if known(context.ref(reference), manifests) and context.ref(reference) not in contexts:
                findings.append(unknown_context(context, reference, field, index))
    for term, entry in context.data.get("language", {}).items():
        if not isinstance(entry, dict) or "from" not in entry:
            continue
        reference, _, name = entry["from"].partition("#")
        source = contexts.get(context.ref(reference))
        if source is None and known(context.ref(reference), manifests):
            findings.append(unknown_context(context, reference, "language", term, "from"))
        elif source is not None and name not in source.data.get("language", {}):
            findings.append(context.finding("unknown-term", f"'{name}' is not a term in {source.id}'s language; add it there, or translate from a term it defines", "language", term, "from"))
    for reference, use in context.data.get("uses", {}).items():
        provider = contexts.get(context.ref(reference))
        if provider is None:
            if known(context.ref(reference), manifests):
                findings.append(unknown_context(context, reference, "uses", reference))
            continue
        provided = provider.data.get("provides", {})
        for index, name in enumerate(use.get("contracts", [])):
            contract = provided.get(name)
            if contract is None:
                findings.append(context.finding("unknown-contract", f"{provider.id} doesn't provide {name}; add it to its provides, or correct the name", "uses", reference, "contracts", index))
            elif contract.get("status") == "deprecated":
                findings.append(context.finding("deprecated-contract", f"{provider.id} has deprecated {name}; move to the contract that replaces it", "uses", reference, "contracts", index))
            elif not contract.get("published") and use["model"] != "share":
                findings.append(context.finding("unpublished-contract", f"{provider.id} hasn't published {name}, so it can change without warning; ask its owner to publish it, or share a kernel instead", "uses", reference, "contracts", index))
        domain = context.data.get("classification", {}).get("domain")
        theirs = provider.data.get("classification", {}).get("domain")
        if use["model"] == "conform" and domain == "core" and theirs is not None and theirs != "core":
            findings.append(context.finding("core-conforms", f"{context.id} is core but conforms to {provider.id}, which is {theirs}; translate its model into this one's instead", "uses", reference, "model"))
    return findings


def agreements(context: Context, contexts: dict[str, Context]) -> list[Finding]:
    findings = []
    for index, reference in enumerate(context.data.get("partners", [])):
        other = contexts.get(context.ref(reference))
        if other is not None and context.id not in map(other.ref, other.data.get("partners", [])):
            findings.append(context.finding("one-sided-partnership", f"{other.id} doesn't list {context.id} as a partner; a partnership needs both sides, so add it there or remove it here", "partners", index))
    for reference, use in context.data.get("uses", {}).items():
        other = contexts.get(context.ref(reference))
        if use["model"] != "share" or other is None:
            continue
        shared = any(other.ref(theirs) == context.id and their_use["model"] == "share" for theirs, their_use in other.data.get("uses", {}).items())
        if not shared:
            findings.append(context.finding("one-sided-shared-kernel", f"{other.id} doesn't share a kernel with {context.id}; add a use with model share there, or translate here", "uses", reference, "model"))
    return findings


def invariants(context: Context) -> list[Finding]:
    findings = []
    aggregates = context.data.get("aggregates", {})
    for name, invariant in context.data.get("invariants", {}).items():
        for index, aggregate in enumerate(invariant.get("applies_to", [])):
            if aggregate not in aggregates:
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
    partners = b.id in map(a.ref, a.data.get("partners", [])) and a.id in map(b.ref, b.data.get("partners", []))
    shared = any(a.ref(reference) == b.id and use["model"] == "share" for reference, use in a.data.get("uses", {}).items())
    return partners or shared


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


def matched(root: Path, pattern: str) -> set[Path]:
    return {path for path in root.glob(f"{pattern}/*" if pattern.endswith("**") else pattern) if path.is_file()}


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


def check_repository(manifests: list[Manifest]) -> list[Finding]:
    findings = []
    for manifest in manifests:
        owners: dict[Path, str] = {}
        for context in manifest.contexts:
            claimed: set[Path] = set()
            for index, pattern in enumerate(context.data.get("code", [])):
                files = matched(context.root, pattern)
                if not files:
                    findings.append(context.finding("missing-path", f"no file in {context.root} matches {pattern}; correct the glob, or remove it", "code", index))
                claimed |= files
            for path in sorted(claimed):
                if path in owners:
                    findings.append(context.finding("overlapping-code", f"{path.relative_to(context.root)} is in the code of both {owners[path]} and {context.id}; give each file to one context", "code"))
                owners.setdefault(path, context.id)
            for reference, keys in code_refs(context):
                findings += symbol(context, reference, keys)
    return findings


def symbol(context: Context, reference: str, keys: tuple[str | int, ...]) -> list[Finding]:
    file, _, name = reference.partition("#")
    path = context.root / file
    if not path.is_file():
        return [context.finding("missing-path", f"{file} doesn't exist in {context.root}; correct the path, or remove it", *keys)]
    text = path.read_text(errors="replace")
    missing = [part for part in name.split(".") if part and not re.search(rf"\b{re.escape(part)}\b", text)]
    if missing:
        return [context.finding("missing-symbol", f"{file} never mentions {missing[0]}; correct the symbol, or point at the file that defines it", *keys)]
    return []
