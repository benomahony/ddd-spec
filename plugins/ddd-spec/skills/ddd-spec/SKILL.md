---
name: ddd-spec
description: Read, follow and edit ddd-spec domain models, the ddd.yaml manifest at a repository's root and the context files it lists. Use this whenever a repository has a ddd.yaml, before changing code there, so the change keeps to its bounded context's language, invariants and contracts. Also use it when someone asks to create, update, review or fix a ddd.yaml or a context file, to turn a whiteboard sketch, notes, an event storming board or a diagram into a model, or talks about bounded contexts, ubiquitous language, invariants, context maps or upstream and downstream dependencies in a codebase, even if they don't mention ddd-spec by name.
---

# ddd-spec

A ddd-spec model is a repository's domain model written down next to its code: which bounded contexts it holds, what their words mean, which rules every change must preserve, and how the contexts depend on each other. `ddd.yaml` at the repository root is the manifest; it lists each context, inline or as a context file. The specification is in [references/spec.md](references/spec.md); read the sections you need when a field or rule isn't covered here.

The model is only worth having while it matches the code, and you are often the one changing the code. So treat it as both a guide and something you keep true.

## Before changing code

1. **Find the file's context.** Read `ddd.yaml` and the context files it lists, and pick the context whose `code` globs include the file. Globs are relative to the repository root and read in order: `**` crosses directories, `*` doesn't, and a glob starting with `!` takes files back out of the ones before it. If the file is listed under `implements`, its context is defined in another manifest, named in `imports`; read that manifest if you can reach it.
2. **Speak its language.** Name new things with the terms its `language` defines, and never with a word listed under a term's `not`, plurals included. If `language` says a commitment is "funds reserved, paid or not", don't call it a payment.
3. **Keep its invariants true.** Every invariant with `status: implemented` is a promise the code makes. If you touch the code in its `enforced_by`, or change behaviour its `verified_by` tests cover, run those tests. Don't weaken a rule to make a change fit; if the rule itself should change, say so and change the model too.
4. **Mind who depends on it.** Before changing anything a context `provides`, look for every context whose `uses` lists it, in this manifest and in the imports. A `published` contract changes only by a new version, so add the new version alongside the old rather than changing it in place.
5. **Update the model in the same change.** A new concept, rule or dependency belongs in the model as well as the code, in the same commit.

## Editing a model

The model records facts, so a wrong fact is worse than a missing one. Absent means undocumented: leave out what you don't know rather than guess it, and ask about business meaning you can't read from the code or docs.

* **Each fact is declared once, by whoever owns it.** A context lists what it `provides` and what it `uses`. Never write down who is upstream; it follows from who owns the contract.
* **Status is a claim; links are evidence.** Mark an invariant `implemented` only when you can point `enforced_by` or `verified_by` at real code or tests. Otherwise it is `proposed`, which is still worth recording.
* **Ids are stable.** Context names, term ids, aggregate, policy and invariant names are lowercase words joined by hyphens. To change how people write a term, set its `term`; don't rename its id, because other contexts refer to it.
* **Words belong to a context.** The same word can mean different things in two contexts. When one context's term translates another's, record it with `from: <context>#<term id>`.

Common edits:

```yaml
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
  BudgetExceeded: { kind: event, published: true, version: "1" }
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

A context owns the commands and queries it accepts and the events it emits. `model` is `translate` when the context turns the other's model into its own words (an anticorruption layer), `conform` when it adopts it as is, and `share` for a shared kernel, which names the files it shares in `code` instead of `contracts`. Pin a used contract to the version the context was built against, as `Name@version`. A test named by a string, as in Zig, Jest or RSpec, is linked as `path#"test name"`.

These mistakes are easy to make, and the schema or a linter will report them:

* `ddd_spec_version` is a quoted string, `"0.1"`, not a number.
* Every other manifest a file refers to, by `<manifest id>/<context>`, must appear in `imports`.
* A published contract needs a `version`; `conform` and `translate` need `contracts`; `share` needs `code`.
* Paths and globs never start with `/` or contain `..`.
* YAML anchors, aliases and tags aren't allowed.

## Writing a first model

Start small: one context, the one being changed, is useful on its own. Find contexts where a word changes meaning, or where code changes for different reasons or at a different pace. For each, write its `purpose` and `code`, then its `language`: the terms the code and its people use, defined in a sentence that draws the term's edge. Add invariants you can find enforced in code or tests, as `implemented` with their evidence, and the ones people tell you about as `proposed`. Add dependencies from what the code actually calls, sends or subscribes to.

When the starting point is a whiteboard, notes or a diagram, turn boxes into contexts, arrows into `provides` and `uses`, and sticky notes about meaning into `language`. Ask before recording anything the sketch leaves ambiguous.

## Checking your work

1. **The schema** checks each file on its own. With this skill's plugin installed in Claude Code, that happens after every edit. Otherwise run:
   ```sh
   uvx --with rfc3986-validator check-jsonschema --schemafile https://benomahony.github.io/ddd-spec/v<version>/ddd.schema.json ddd.yaml <context files>
   ```
   where `<version>` is the manifest's `ddd_spec_version`, such as `0.1`.
2. **A compatible linter** checks the rules that span files and the code: references that resolve, contracts that are published and current, words a context bans appearing in its code, and more. If the repository uses one, run it after changing the model or the code it links to. The checks page of the specification lists every rule.

Report what you actually checked. If neither the schema nor a linter ran, say that the model is unchecked rather than implying it is valid.
