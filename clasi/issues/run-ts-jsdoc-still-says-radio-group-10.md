---
title: "src/blocks/run.ts JSDoc still says enableRadioLink() uses radio group 10"
status: pending
created: 2026-09-06
---

# `run.ts` JSDoc still says `enableRadioLink()` uses "group 10"

Sprint 035 ticket 006 fixed the stale radio-address claims in plain
`//` comments (`test/test.ts`) but was forbidden from touching
`/** ... */` JSDoc in `src/blocks/*.ts`, because JSDoc is the
student-facing block help PXT renders. The one surviving stale claim
is inside JSDoc: `src/blocks/run.ts`, `enableRadioLink()`'s doc block,
the continuation line `* time -- and group 10.` (and `setupRadio`'s
"The group defaults to 10, the relay's listen group", which is a
separate, still-true statement about the block's default argument).

The true statement: `enableRadioLink()` uses the channel AND group
that `tools/make_deploy.py` injected for that board (`kChannel` /
`kGroup` in `src/comms/radio_transport.h`); nothing is fixed at 10.
See `.claude/rules/playfield-testing.md`'s fleet table.

Fix: a one-line JSDoc text edit in `run.ts`, with JSDoc explicitly in
scope. Do not change `setupRadio`'s `group: number = 10` default (code,
student-facing signature). Run `tests/host/test_typescript_typecheck.py`
and `tests/host/test_block_toolbox_order.py` after.
