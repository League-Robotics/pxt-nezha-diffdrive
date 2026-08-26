---
status: done
sprint: '017'
tickets:
- 017-001
---

# `clasi design validate` fails -- sprint 013's five new `src/` directories have no `DESIGN.md`

Priority: **High** -- the process gate the review guidelines require is red
right now, and it went red inside a sprint whose final ticket was scoped as a
sweep.

## Current output

```
Missing design doc: subsystem directory src/blocks   has no DESIGN.md
Missing design doc: subsystem directory src/comms    has no DESIGN.md
Missing design doc: subsystem directory src/core     has no DESIGN.md
Missing design doc: subsystem directory src/motion   has no DESIGN.md
Missing design doc: subsystem directory src/platform has no DESIGN.md
```

`.clasi/config.yaml` declares `sources: [src, tools, tests, test]`. Sprint 013
grouped `src/` into five directories by dependency layer; under the CLASI doc
model each becomes a subsystem needing a co-located `DESIGN.md`.

`docs/code-review/guidelines.md` Phase 0 states it flatly: *"The doc set must
pass `clasi design validate`."*

`src/DESIGN.md`'s preamble names the tension and argues past it -- *"the
directory split is coarse (five buckets for eleven layers), so it doesn't carry
the fine-grained per-file detail below -- this document still carries the
logical subsystem breakdown as sections."* That is a reasonable position on
**where the detail lives**. It is not a resolution of the validator failure, and
nothing in the repo records it as a deliberate deviation.

## What to change

Preferred: five thin `src/<dir>/DESIGN.md` files -- a paragraph of scope plus a
pointer into the matching `src/DESIGN.md` section. This is exactly the pattern
`tests/DESIGN.md` -> `tests/host/DESIGN.md` already uses, and it makes a
directory a reader can `ls` into self-describing.

Alternative: re-declare `sources:` to name the five directories explicitly, if
the intent is that `src/` is one subsystem that happens to have folders.

## Recurrence guard

Sprint 013 ticket 006 did not run the validator. Whatever the sprint-close
checklist is, `clasi design validate` should be on it.

Detail: [`docs/code-review/2026-08-26/raw/design-docs.md`](docs/code-review/2026-08-26/raw/design-docs.md) (D-01).
