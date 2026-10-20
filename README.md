# ddd.yaml

A file format for domain models: bounded contexts, the language each one speaks, how they relate, and the aggregates inside them. People, coding agents and tools all read the same file.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/benomahony/ddd-spec/main/ddd.schema.json
ddd: 1
kind: BoundedContext
id: acme/billing
purpose: Turn fulfilled orders into invoices and collect payment.
owner: team/money
language:
  invoice: A request for payment for one fulfilled order.
  customer:
    means: The party an invoice is addressed to and who owes payment.
    not: [client, user]
outbound:
  - to: acme/shipping
    event: InvoicePaid
    contract: asyncapi.yaml#/channels/invoicePaid
relationships:
  - with: acme/shipping
    pattern: upstream-downstream
    side: upstream
    as: [open-host-service, published-language]
```

## Principles

1. **Familiar words.** Fields follow the [Bounded Context Canvas](https://github.com/ddd-crew/bounded-context-canvas) and the [Aggregate Design Canvas](https://github.com/ddd-crew/aggregate-design-canvas). Relationship patterns follow [Context Mapper](https://contextmapper.org/docs/context-map/).
2. **Owners write locally, and the map is computed.** Each context declares its own side of every relationship, in its own repository. The context map is built from those declarations, and two sides that disagree is a finding.
3. **No global vocabulary.** A word means something only inside a context. Translations between contexts are written down with `from`.
4. **Contracts live elsewhere.** A message points to its OpenAPI or AsyncAPI definition instead of repeating it.
5. **Plain language.** A term can be just `term: definition`.

## Files

A repository describes its model in `ddd.yaml` at its root or in any `*.ddd.yaml` file. A file holds one or more documents separated by `---`. The schema in [`ddd.schema.json`](https://github.com/benomahony/ddd-spec/blob/main/ddd.schema.json) applies to each document.

Every document has:

| Field | Meaning |
|---|---|
| `ddd` | The version of this specification, currently `1` |
| `kind` | `BoundedContext`, `Aggregate` or `ContextMap` |
| `id` | A path naming it across every repository, such as `acme/billing` |

Any field starting with `x-` is an extension and is ignored by tools that don't know it.

## BoundedContext

| Field | Meaning |
|---|---|
| `purpose` | Required. Why the context exists, in the business's words |
| `name`, `owner` | A display name, and the team accountable for it |
| `classification` | `domain` (`core`, `supporting`, `generic`), `business_model` (`revenue`, `engagement`, `compliance`, `cost-reduction`) and `evolution` (`genesis`, `custom-built`, `product`, `commodity`) |
| `roles` | Domain roles such as `execution`, `analysis` or `gateway` |
| `language` | Each term, mapped to its definition or to `means`, `not` (words that must not stand in for it) and `from` (`<context id>#<term>` it translates) |
| `decisions` | Business rules the context enforces |
| `inbound`, `outbound` | Messages received `from` or sent `to` another context: exactly one of `command`, `query` or `event`, and an optional `contract` |
| `relationships` | This context's side of each relationship, described below |
| `assumptions`, `open_questions` | What the model takes for granted, and what it has yet to settle |

### Relationships

| Field | Meaning |
|---|---|
| `with` | The other context's `id` |
| `pattern` | `partnership`, `shared-kernel` or `separate-ways`, which are symmetric, or `customer-supplier` or `upstream-downstream` |
| `side` | `upstream` or `downstream`. Required for the asymmetric patterns, and not allowed for the symmetric ones |
| `as` | Roles this side plays: `open-host-service` or `published-language` upstream, `anticorruption-layer` or `conformist` downstream |

Message direction and the relationship are separate on purpose. A command can flow from a downstream context to its upstream context.

## Aggregate

The `id` extends its context's, such as `acme/billing/Invoice`.

| Field | Meaning |
|---|---|
| `description` | What the aggregate is responsible for |
| `handles`, `emits` | The commands it accepts and the events it raises |
| `states` | The states it moves through |
| `invariants` | Statements that are true after every command |
| `corrective_policies` | What restores an invariant that can only be fixed after the fact |

## ContextMap

Optional. It names a landscape (`name`, `description`) and lists `sources`, such as other repositories, where more of its documents live.

## Conformance

| Level | A tool checks that |
|---|---|
| L1 | each document is valid against the schema |
| L2 | every `id` a document refers to resolves, and the two sides of every relationship and message agree |
| L3 | the code agrees with the model, for example that no `not` word is used inside a context |

## Validating

```sh
uvx check-jsonschema --schemafile ddd.schema.json ddd.yaml
```

Editors running the YAML language server validate and complete a file with the `$schema` comment shown at the top.

## Contributing

`tests/valid` holds documents the schema must accept and `tests/invalid` documents it must reject, each with exactly one fault. Any change to the schema comes with fixtures for it, and other implementations can test themselves against the same files.

The [site](https://benomahony.github.io/ddd-spec) is built with [Zine](https://zine-ssg.io) from this README. After changing it, run `python3 docs/sync.py` to regenerate the pages, and `zine` in `docs` to preview them.
