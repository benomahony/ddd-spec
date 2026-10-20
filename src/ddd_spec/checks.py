from ddd_spec.load import Document, Finding

ASYMMETRIC = {"customer-supplier", "upstream-downstream"}
MESSAGE_KINDS = ("command", "query", "event")
DIRECTIONS = (("outbound", "to", "inbound", "from"), ("inbound", "from", "outbound", "to"))


def check_model(documents: list[Document]) -> list[Finding]:
    findings = duplicate_ids(documents)
    contexts = {document.id: document for document in documents if document.kind == "BoundedContext"}
    for document in documents:
        if document.kind == "BoundedContext":
            findings += references(document, contexts) + relationships(document, contexts) + messages(document, contexts)
        if document.kind == "Aggregate":
            findings += aggregate_context(document, contexts)
    return findings


def duplicate_ids(documents: list[Document]) -> list[Finding]:
    seen: dict[str, Document] = {}
    findings = []
    for document in documents:
        if document.id in seen:
            findings.append(document.finding("duplicate-id", f"'{document.id}' is already the id of a document in {seen[document.id].path}; give each document its own id", "id"))
        seen.setdefault(document.id, document)
    return findings


def unknown_context(document: Document, id: str, *keys: str | int) -> Finding:
    return document.finding("unknown-context", f"no bounded context has the id '{id}'; check the spelling, or pass the file that defines it", *keys)


def references(context: Document, contexts: dict[str, Document]) -> list[Finding]:
    findings = []
    for index, relationship in enumerate(context.data.get("relationships", [])):
        if relationship["with"] not in contexts:
            findings.append(unknown_context(context, relationship["with"], "relationships", index, "with"))
    for direction, peer, _, _ in DIRECTIONS:
        for index, message in enumerate(context.data.get(direction, [])):
            if message[peer] not in contexts:
                findings.append(unknown_context(context, message[peer], direction, index, peer))
    for term, entry in context.data.get("language", {}).items():
        if not isinstance(entry, dict) or "from" not in entry:
            continue
        source, _, name = entry["from"].partition("#")
        if source not in contexts:
            findings.append(unknown_context(context, source, "language", term, "from"))
        elif name not in contexts[source].data.get("language", {}):
            findings.append(context.finding("unknown-term", f"'{name}' is not a term in {source}'s language; add it there, or translate from a term it defines", "language", term, "from"))
    return findings


def relationships(context: Document, contexts: dict[str, Document]) -> list[Finding]:
    findings = []
    for index, ours in enumerate(context.data.get("relationships", [])):
        other = contexts.get(ours["with"])
        if other is None or other.id == context.id:
            continue
        theirs = next((relationship for relationship in other.data.get("relationships", []) if relationship["with"] == context.id), None)
        if theirs is None:
            findings.append(context.finding("one-sided-relationship", f"{other.id} doesn't declare its side of this relationship; add a relationship with {context.id} to it", "relationships", index))
        elif context.id > other.id:
            continue
        elif theirs["pattern"] != ours["pattern"]:
            findings.append(context.finding("relationship-mismatch", f"{context.id} calls this relationship {ours['pattern']} but {other.id} calls it {theirs['pattern']}; agree on one pattern", "relationships", index, "pattern"))
        elif ours["pattern"] in ASYMMETRIC and theirs["side"] == ours["side"]:
            findings.append(context.finding("relationship-mismatch", f"{context.id} and {other.id} both say they are {ours['side']}; make one side upstream and the other downstream", "relationships", index, "side"))
    return findings


def messages(context: Document, contexts: dict[str, Document]) -> list[Finding]:
    findings = []
    for direction, peer, opposite, opposite_peer in DIRECTIONS:
        for index, message in enumerate(context.data.get(direction, [])):
            other = contexts.get(message[peer])
            if other is None:
                continue
            kind = next(kind for kind in MESSAGE_KINDS if kind in message)
            matched = any(theirs.get(opposite_peer) == context.id and theirs.get(kind) == message[kind] for theirs in other.data.get(opposite, []))
            if not matched:
                findings.append(context.finding("unmatched-message", f"{other.id} has no {opposite} {kind} {message[kind]} {opposite_peer} {context.id}; add it there, or remove this one", direction, index, kind))
    return findings


def aggregate_context(aggregate: Document, contexts: dict[str, Document]) -> list[Finding]:
    parent = aggregate.id.rpartition("/")[0]
    if parent in contexts:
        return []
    return [aggregate.finding("unknown-context", f"an aggregate's id extends its bounded context's, and no bounded context has the id '{parent}'; check the spelling, or pass the file that defines it", "id")]
