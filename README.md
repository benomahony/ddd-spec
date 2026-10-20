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
provides:
  ReserveFunds: { kind: command }
uses:
  acme.expenses/claims:
    model: translate
    contracts: [ExpenseApproved@1]
policies:
  reserve-approved-expenses:
    when: acme.expenses/claims#ExpenseApproved
    then: [ReserveFunds]
```

## Principles

1. **Built for the change in front of you.** From a file, find its context; from the context, its words, its rules, the evidence that they hold, and who depends on it. `ddd-spec explain` prints exactly that.
2. **Each fact is declared once, by whoever owns it.** A context lists the contracts it provides and the contracts it uses. Who is upstream follows from those facts, so it can never contradict them.
3. **Words belong to a context.** The same word may mean different things in different contexts, and a translation between them is written down.
4. **Absent means undocumented, but a name must resolve.** A model can describe as much or as little as is known, yet a misspelt name is an error, not an unknown.
5. **Claims are not evidence.** `implemented` is what the author says; the linked code and tests are what a reader can check.
6. **Contracts live elsewhere.** A contract points at its OpenAPI or AsyncAPI definition instead of repeating it.

## Getting started

Write a `ddd.yaml` at the root of your repository, then check it and the code it points at:

```sh
uvx ddd-spec check
```

Before changing a file, ask which contexts it belongs to and what they promise:

```sh
uvx ddd-spec explain src/budgeting/budget.py
```

Until the validator is on PyPI, run it with `uvx --from git+https://github.com/benomahony/ddd-spec ddd-spec`.

## Documentation

* [Getting started](https://benomahony.github.io/ddd-spec/getting-started/): model one context, link it to the code, and grow from there.
* [Modelling guide](https://benomahony.github.io/ddd-spec/guide/): choosing contexts, writing their language, recording rules and evidence, and connecting repositories.
* [Specification 0.1](https://benomahony.github.io/ddd-spec/specification/): every field and rule, normatively.
* [Checks](https://benomahony.github.io/ddd-spec/checks/): every rule a tool checks, each with a model that breaks it.
* [Command line](https://benomahony.github.io/ddd-spec/cli/): `ddd-spec check` and `ddd-spec explain`.

## Contributing

Each version of the specification lives in `spec/v<version>/`: its text, `spec.md`, and its schema, `ddd.schema.json`. That folder is the only place a version is defined, and a released version's folder never changes; the next version starts as a copy in a new folder.

`tests/valid` holds files the schema must accept and `tests/invalid` files it must reject, each with exactly one fault. `tests/models/valid` is a repository whose model agrees with itself and its code, and each directory in `tests/models/invalid` breaks only the rule it is named after. Every rule in the specification has one, and other implementations can test themselves against the same files. `uv run pytest` runs them all.

The [site](https://benomahony.github.io/ddd-spec) is built with [Zine](https://zine-ssg.io). Its home page comes from this README, its specification and checks pages from `spec/` and the test models, and its guides from `docs/content`. After changing any of them, run `uv run python docs/sync.py` to regenerate the pages, and `zine` in `docs` to preview them.

A commit that passes CI on `main` and changes the validator or the specification is released, as the latest specification version with the next patch number. Releases also go to PyPI once the repository's `PUBLISH_TO_PYPI` variable is `true`, after setting up trusted publishing for the Release workflow on PyPI.

## License

MIT
