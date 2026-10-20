# ddd-spec

A domain model that lives next to the code: which bounded contexts a repository holds, what their words mean, which rules every change must preserve, and how the contexts depend on each other. People, coding agents and tools all read the same files.

```yaml
# ddd.yaml
# yaml-language-server: $schema=https://benomahony.github.io/ddd-spec/v0.1/ddd.schema.json
ddd_spec_version: "0.1"
id: acme.events
contexts:
  budgeting: domains/budgeting.yaml
```

```yaml
# domains/budgeting.yaml
# yaml-language-server: $schema=https://benomahony.github.io/ddd-spec/v0.1/ddd.schema.json
purpose: Control the full committed cost of an event.
scope:
  includes: [Allocating event budgets, Reserving funds for event expenditure]
  excludes: [Reimbursing employees]
code: ["src/budgeting/**"]
language:
  commitment:
    means: Funds reserved for approved expenditure, whether or not it has been paid.
    from: acme.expenses/claims#approved expense
  available budget: The event's approved allocation minus its active commitments.
invariants:
  within-allocation:
    statement: Active commitments never exceed the approved allocation.
    status: implemented
    enforced_by: [src/budgeting/budget.py#EventBudget.reserve]
    verified_by: [tests/test_budget.py#test_rejects_commitment_above_allocation]
uses:
  acme.expenses/claims:
    model: translate
    contracts: [ExpenseApproved]
```

## Principles

1. **Built for the change in front of you.** From a file, find its context; from the context, its words, its rules and the evidence that they hold. `ddd explain` does exactly that.
2. **Each fact is declared once, by whoever owns it.** A context lists the contracts it provides and the contracts it uses. Who is upstream, and every pattern from Evans's *Domain-Driven Design*, follows from those facts rather than being declared beside them.
3. **Words belong to a context.** The same word may mean different things in different contexts, and a translation between them is written down.
4. **Absent means undocumented.** A model can describe as much or as little as is known. A missing declaration never means that something doesn't exist.
5. **Claims are not evidence.** `implemented` is what the author says; the linked code and tests are what a reader can check.
6. **Contracts live elsewhere.** A contract points at its OpenAPI or AsyncAPI definition instead of repeating it.

## Files

A repository has one `ddd.yaml` at its root: the manifest. It lists every bounded context, by name, either as a context file relative to the manifest or inline. Tools read only the files the manifest lists.

| Field | Meaning |
|---|---|
| `ddd_spec_version` | The version of this specification, currently `"0.1"` |
| `id` | A name for the manifest unique across every repository, such as `acme.events` |
| `name` | A display name |
| `contexts` | Each context's name, mapped to its file or to the context itself |

A context's id is the manifest's id and its name: `acme.events/budgeting`. Within a manifest, a context is referred to by its name alone; from another manifest, by its full id. A repository may hold several contexts, and several repositories may depend on each other's contexts.

Paths and globs are relative to the repository root, use `/`, and are case-sensitive. A reference to code is a path, optionally followed by `#` and a symbol: `src/budgeting/budget.py#EventBudget.reserve`.

Any field starting with `x-` is an extension, and tools that don't know it ignore it. Any other unknown field is an error.

While the specification is at 0.x, each minor version may change what a file means, so `ddd_spec_version` names one; the schema for it lives at `https://benomahony.github.io/ddd-spec/v0.1/ddd.schema.json`.

## Contexts

Only `purpose` is required.

| Field | Meaning |
|---|---|
| `purpose` | The business responsibility of the context |
| `name`, `owner` | A display name, and the team accountable for it |
| `classification` | Its `domain`: `core`, `supporting` or `generic` |
| `scope` | What it `includes` and what it `excludes`, in sentences |
| `code` | Globs for the files that implement it |
| `language` | Its terms, described below |
| `aggregates`, `invariants` | Its consistency boundaries and rules, described below |
| `provides`, `uses`, `customers`, `partners` | Its contracts and dependencies, described below |

### Language

Each term maps to its definition, or to these fields:

| Field | Meaning |
|---|---|
| `means` | Required. What the term means in this context |
| `not` | Words that must not stand in for it here |
| `from` | The term in another context it is translated from, as `<context>#<term>` |
| `code` | The symbols that implement it |

### Aggregates and invariants

An aggregate has an optional `purpose`, a `root` symbol and a `status`. An invariant has:

| Field | Meaning |
|---|---|
| `statement` | Required. The rule, as a sentence that is true after every change |
| `status` | Required. `proposed`, `implemented` or `deprecated` |
| `applies_to` | The aggregates whose boundary holds it, once that is decided |
| `enforced_by` | The code that keeps it true |
| `verified_by` | The tests or checks that show it holds |

An invariant can be recorded before anyone knows which aggregate will hold it. A proposed rule never becomes a guarantee by being written down.

### Contracts and dependencies

| Field | Meaning |
|---|---|
| `provides` | The contracts the context owns, by name: each with a `kind` (`command`, `query` or `event`), and optionally what it `means`, whether it is `published`, its `status`, and where it is `defined_in` |
| `uses` | Each context whose model this one depends on, with its `model` (`conform`, `translate` or `share`) and the `contracts` it uses |
| `customers` | Contexts whose needs this one plans for |
| `partners` | Contexts this one plans together with; both sides list each other |

The owner of a contract is upstream of those that use it, whichever way its messages flow: a context owns the commands and queries it accepts and the events it emits. A published contract is versioned, and others may rely on it.

Evans's patterns are derived, not declared:

| Pattern | Holds when |
|---|---|
| Open host service, published language | the contract is `published` |
| Anticorruption layer | the downstream context has `model: translate` |
| Conformist | the downstream context has `model: conform`, and the upstream doesn't list it in `customers` |
| Customer and supplier | the upstream context lists the downstream one in `customers` |
| Partnership | both contexts list each other in `partners` |
| Shared kernel | both contexts use each other with `model: share` |

## Conformance

A tool reports each level separately, because each establishes something different.

| Level | Establishes |
|---|---|
| 1. Structure | each file is valid against the schema |
| 2. References | every context, contract, term and aggregate referred to exists, and the landscape has no structural faults |
| 3. Repository links | every path and symbol referred to exists, and no file belongs to two contexts |
| 4. Evidence | the linked tests and checks run and pass |

A valid model doesn't establish that the domain is modelled well, and a listed invariant doesn't enforce itself. References into a manifest that wasn't loaded are left unchecked rather than reported, since absent means undocumented.

## Validating

The reference validator, `ddd`, checks levels 1 to 3. Pass it other repositories' manifests to check the references between them.

```console
$ uvx --from git+https://github.com/benomahony/ddd-spec ddd check
domains/budgeting.yaml:31:17  error  unpublished-contract  acme.events/expenses hasn't published ExpenseApproved, so it can change without warning; ask its owner to publish it, or share a kernel instead
ddd: 1 problem in the model and no problems in its links to the code, across 2 contexts
```

| Level | Check | Reported when |
|---|---|---|
| 1 | `invalid-yaml` | a file doesn't parse |
| 1 | `invalid-document` | a file breaks the schema |
| 1 | `missing-file` | the manifest lists a context file that doesn't exist |
| 2 | `duplicate-id` | two manifests share an `id` |
| 2 | `unknown-context` | a reference names a context its manifest doesn't define |
| 2 | `unknown-contract` | a context uses a contract the other doesn't provide |
| 2 | `unknown-term` | a `from` names a term its context doesn't define |
| 2 | `unknown-aggregate` | an invariant applies to an aggregate its context doesn't define |
| 2 | `unpublished-contract` | a context relies on a contract that hasn't been published |
| 2 | `deprecated-contract` | a context uses a deprecated contract |
| 2 | `core-conforms` | a core context conforms to a context that isn't core |
| 2 | `one-sided-partnership` | only one context lists a partnership |
| 2 | `one-sided-shared-kernel` | only one context shares a kernel |
| 2 | `dependency-cycle` | contexts depend on each other without being partners or sharing a kernel |
| 2 | `implemented-without-evidence` | an implemented invariant names no code or test |
| 3 | `missing-path` | a glob or path matches no file |
| 3 | `missing-symbol` | a file never mentions the symbol named |
| 3 | `overlapping-code` | a file is in the code of two contexts |

It exits 1 when it finds a problem, and 2 when there is no manifest. Problems in the files themselves stop it before the other levels, which rely on valid files.

Before changing a file, ask which contexts it belongs to, and get their scope, language, invariants and contracts:

```sh
ddd explain src/budgeting/budget.py
```

Any JSON Schema validator checks level 1 alone, and editors running the YAML language server validate and complete a file with the `$schema` comment shown at the top.

## Contributing

`tests/valid` holds files the schema must accept and `tests/invalid` files it must reject, each with exactly one fault. `tests/models/valid` is a repository whose model agrees with itself and its code, and each directory in `tests/models/invalid` is one that fails only the check it is named after. Any change to the schema or the checks comes with fixtures, and other implementations can test themselves against the same files. `uv run pytest` runs them all.

The [site](https://benomahony.github.io/ddd-spec) is built with [Zine](https://zine-ssg.io) from this README. After changing it, run `python3 docs/sync.py` to regenerate the pages, and `zine` in `docs` to preview them.

Every commit that passes CI on `main` is released one patch version up, with the validator and the schema attached. Run the Release workflow by hand to raise the minor or major version instead.
