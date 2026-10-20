# ddd-spec

A domain model that lives next to the code: which bounded contexts a repository holds, what their words mean, which rules every change must preserve, and how the contexts depend on each other. People, coding agents and tools all read the same files.

```yaml
# ddd.yaml
# yaml-language-server: $schema=https://benomahony.github.io/ddd-spec/v0.1/ddd.schema.json
ddd_spec_version: "0.1"
id: acme.events
imports:
  acme.expenses: https://raw.githubusercontent.com/acme/expenses/main/ddd.yaml
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
    not: [hold]
    from: acme.expenses/claims#approved-expense
  available-budget: The event's approved allocation minus its active commitments.
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

1. **Built for the change in front of you.** From a file, find its context; from the context, its words, its rules, the evidence that they hold, and who depends on it. `ddd-spec explain` does exactly that.
2. **Each fact is declared once, by whoever owns it.** A context lists the contracts it provides and the contracts it uses. Who is upstream follows from those facts rather than being declared beside them.
3. **Words belong to a context.** The same word may mean different things in different contexts, and a translation between them is written down.
4. **Absent means undocumented, but a name must resolve.** A model can describe as much or as little as is known. Every manifest a file refers to is declared, so a misspelt name is an error, not an unknown.
5. **Claims are not evidence.** `implemented` is what the author says; the linked code and tests are what a reader can check.
6. **Contracts live elsewhere.** A contract points at its OpenAPI or AsyncAPI definition instead of repeating it.

## Files

The key words MUST, MUST NOT, SHOULD and MAY are to be read as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

A repository that describes its model MUST have one manifest, `ddd.yaml`, at its root. The manifest MUST list every context the repository defines, each either as a context file or inline. A tool MUST read only the files the manifest lists and the manifests it imports.

| Field | Meaning |
|---|---|
| `ddd_spec_version` | Required. The version of this specification the files follow, currently `"0.1"` |
| `id` | Required. A name for the manifest, unique across every repository, such as `acme.events` |
| `name` | A display name |
| `contexts` | Required. Each context's name, mapped to its file or to the context itself |
| `imports` | Every other manifest the files refer to: its id, mapped to a path relative to this manifest or an https URL of its `ddd.yaml` |
| `implements` | Contexts defined in another manifest that this repository holds code for: each one's full id, mapped to its `code` |

Each context file MUST hold exactly one context. Context names, term ids, aggregate names and invariant names MUST be lowercase letters, digits and hyphens.

### References

A context's id is its manifest's id, a `/`, and its name: `acme.events/budgeting`. Within a manifest, a context MAY be referred to by its name alone; from another manifest it MUST be referred to by its full id, and that manifest MUST appear in `imports`. A term is referred to as `<context>#<term id>`. All names and ids are case-sensitive.

A tool MUST report a reference to a manifest that isn't this one and isn't imported. A tool that hasn't loaded an imported manifest MUST NOT report references into it as unknown.

### Paths and globs

Paths and globs are relative to the repository root, use `/`, are case-sensitive, and MUST NOT begin with `/` or contain a `..` segment. A glob matches files only, never directories, using this syntax:

| Pattern | Matches |
|---|---|
| `*` | any characters except `/` |
| `?` | one character except `/` |
| `**/` | zero or more whole directories |
| `**` at the end | everything below that point |

Every other character matches itself. A glob MUST NOT match a file inside a directory whose name starts with `.`, or a file the repository's git configuration ignores.

A reference to code is a path, optionally followed by `#` and a symbol written as the file's own language writes it: `budget.py#EventBudget.reserve`, `budget.rs#EventBudget::reserve`, `Budget.java#Budget#reserve`. A tool SHOULD check that the file defines the symbol's last part, not merely mentions it.

### Extensions and versions

Any field starting with `x-` is an extension, allowed on every object, and a tool MUST ignore extensions it doesn't know. Any other unknown field is an error.

While the specification is at 0.x, each minor version MAY change what a file means, so `ddd_spec_version` names a minor version. Each version's schema is published at `https://benomahony.github.io/ddd-spec/v<version>/ddd.schema.json` and never changes once released; a new version gets a new URL, and old ones stay.

## Contexts

Only `purpose` is required.

| Field | Meaning |
|---|---|
| `purpose` | The business responsibility of the context |
| `name`, `owner` | A display name, and the team accountable for it |
| `status` | `proposed`, `implemented` or `deprecated` |
| `external` | `true` for a system outside the organisation, such as a payment provider, described by those who depend on it. An external context MUST NOT have `code` |
| `classification` | Its `domain`: `core`, `supporting` or `generic` |
| `scope` | What it `includes` and what it `excludes`, in sentences |
| `code` | Globs for the files in this repository that implement it |
| `language` | Its terms, described below |
| `aggregates`, `invariants` | Its consistency boundaries and rules, described below |
| `provides`, `uses`, `customers`, `partners` | Its contracts and dependencies, described below |

A file SHOULD belong to at most one context. Contexts that share a kernel MAY share files.

### Language

Each term id maps to its definition, or to these fields:

| Field | Meaning |
|---|---|
| `means` | Required. What the term means in this context |
| `term` | The term as people write it, when that isn't its id with hyphens read as spaces |
| `not` | Words that MUST NOT stand in for it in the context's code |
| `from` | The term in another context it is translated from |
| `status` | `proposed`, `implemented` or `deprecated` |
| `code` | The symbols that implement it |

A term's id is stable: renaming how people write a term changes `term`, not the id that others refer to.

### Aggregates and invariants

An aggregate has an optional `purpose`, a `root` symbol, a `status`, the commands it `handles` and the events it `emits`, both named from the context's `provides`. An invariant has:

| Field | Meaning |
|---|---|
| `statement` | Required. The rule, as a sentence that is true after every change |
| `status` | Required. `proposed`, `implemented` or `deprecated` |
| `applies_to` | The aggregates whose boundary holds it, once that is decided |
| `enforced_by` | The code that keeps it true |
| `verified_by` | The tests or checks that show it holds |

An invariant MAY be recorded before anyone knows which aggregate will hold it. A tool MUST NOT treat a proposed invariant as a guarantee.

### Contracts and dependencies

| Field | Meaning |
|---|---|
| `provides` | The contracts the context owns, by name, such as `ExpenseApproved` or `expenses.expense-approved.v1`: each with a `kind` (`command`, `query` or `event`), and optionally what it `means`, whether it is `published`, its `version`, its `status`, and where it is `defined_in`. A published contract MUST have a `version` |
| `uses` | Each context whose model this one depends on, with its `model` (`conform`, `translate` or `share`) and the `contracts` it uses |
| `customers` | Contexts whose needs this one plans for |
| `partners` | Contexts this one plans together with. Both sides MUST list each other |

A context owns the commands and queries it accepts and the events it emits. The owner of a contract is upstream of every context that uses it, whichever way its messages flow. Changing a published contract means publishing a new version.

The relationships in Evans's *Domain-Driven Design* can be read from these facts:

| Relationship | Recorded as |
|---|---|
| Open host service, published language | the upstream contract is `published` |
| Anticorruption layer | the downstream context has `model: translate` |
| Conformist | the downstream context has `model: conform` |
| Customer and supplier | the upstream context lists the downstream one in `customers` |
| Partnership | both contexts list each other in `partners` |
| Shared kernel | both contexts use each other with `model: share` |

These are what the files record, not judgements about the teams: whether a conformist downstream conforms by choice or because the upstream won't negotiate is not recorded.

## Conformance

A tool reports each level separately, because each establishes something different.

| Level | Establishes |
|---|---|
| 1. Structure | each file is valid against the schema |
| 2. References | every manifest, context, contract, term and aggregate referred to exists, and the landscape has no structural faults |
| 3. Repository links | every path and symbol referred to exists, files belong to one context unless kernels are shared, and avoided words stay out of the code |
| 4. Evidence | the linked tests and checks run and pass |

A valid model doesn't establish that the domain is modelled well, and a listed invariant doesn't enforce itself. Prose fields, such as `purpose`, `scope`, `means` and `statement`, are for people and agents to read; this version defines no automatic checks of them.

## Validating

The reference validator checks levels 1 to 3:

```sh
uvx ddd-spec check
```

Until it is on PyPI, `uvx --from git+https://github.com/benomahony/ddd-spec ddd-spec check` runs the same thing. It loads the manifest and every import that is a path; `--remote` also fetches imports that are URLs.

```console
$ ddd-spec check
domains/budgeting.yaml:38:17  error  unpublished-contract  acme.events/expenses hasn't published ExpenseApproved, so it can change without warning; ask its owner to publish it, or share a kernel instead
ddd-spec: 1 problem in the model and no problems in its links to the code, across 4 contexts
```

| Level | Check | Reported when |
|---|---|---|
| 1 | `invalid-yaml` | a file doesn't parse |
| 1 | `invalid-document` | a file breaks the schema |
| 1 | `missing-file` | a context file or imported manifest can't be read |
| 2 | `duplicate-id` | two manifests share an `id` |
| 2 | `import-mismatch` | an imported manifest's `id` isn't the one it is imported as |
| 2 | `unknown-manifest` | a reference names a manifest that isn't imported |
| 2 | `unknown-context` | a reference names a context its manifest doesn't define |
| 2 | `unknown-contract` | a context or aggregate names a contract that isn't provided |
| 2 | `wrong-contract-kind` | an aggregate handles something other than a command, or emits something other than an event |
| 2 | `unknown-term` | a `from` names a term its context doesn't define |
| 2 | `unknown-aggregate` | an invariant applies to an aggregate its context doesn't define |
| 2 | `unpublished-contract` | a context relies on a contract that hasn't been published |
| 2 | `deprecated-reference` | a context uses a deprecated context or contract, or translates a deprecated term |
| 2 | `core-conforms` | a core context conforms to a context that isn't core |
| 2 | `customer-without-use` | a context lists a customer that uses none of its contracts |
| 2 | `one-sided-partnership` | only one context lists a partnership |
| 2 | `one-sided-shared-kernel` | only one context shares a kernel |
| 2 | `dependency-cycle` | contexts depend on each other without being partners or sharing a kernel |
| 2 | `implemented-without-evidence` | an implemented invariant names no code or test |
| 3 | `missing-path` | a glob or path matches no file |
| 3 | `missing-symbol` | a file doesn't define the symbol named |
| 3 | `overlapping-code` | a file is in the code of two contexts that share no kernel |
| 3 | `avoided-word` | a context's code uses a word one of its terms says `not` |

It exits 1 when it finds a problem, and 2 when there is no manifest. Problems in the files themselves stop it before the other levels, which rely on valid files.

Before changing a file, ask which contexts it belongs to. `explain` prints each one's scope, language, invariants and contracts, and which contexts use each contract:

```sh
ddd-spec explain src/budgeting/budget.py
```

Any JSON Schema validator checks level 1 alone, and editors running the YAML language server validate and complete a file with the `$schema` comment shown at the top.

## Contributing

`tests/valid` holds files the schema must accept and `tests/invalid` files it must reject, each with exactly one fault. `tests/models/valid` is a repository whose model agrees with itself and its code, and each directory in `tests/models/invalid` is one that fails only the check it is named after. Any change to the schema or the checks comes with fixtures, and other implementations can test themselves against the same files. `uv run pytest` runs them all.

Each spec version's schema lives in `schema/v<version>/`, which is the only place the version is defined. A released version's folder never changes; the next version starts as a copy in a new folder.

The [site](https://benomahony.github.io/ddd-spec) is built with [Zine](https://zine-ssg.io) from this README. After changing it, run `python3 docs/sync.py` to regenerate the pages, and `zine` in `docs` to preview them.

A commit that passes CI on `main` and changes the validator or the schema is released, as the latest spec version with the next patch number. Releases also go to PyPI once the repository's `PUBLISH_TO_PYPI` variable is set to `true`, after setting up trusted publishing for the Release workflow on PyPI.
