---
status: in-progress
sprint: '032'
tickets:
- 032-004
---

# RUN dispatch contract: snapshot arguments per dispatch; document that handlers run on the wire's fiber

Priority: **Medium** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: BT-02 (API half), BT-03 ([blocks-and-test](../../../docs/code-review/2026-09-02/raw/blocks-and-test.md)). Triage #8.

## Description

`run.ts:43-58`'s registered callback reassigns the module-level `runParts`.
`protocol.cpp:283-297` dispatches `abort`/`clearestop` nested inside a
running job's tick loop, so the nested call overwrites `runParts` and the
outer handler's later `runArg(i)` describes the abort. `protocol.h:180-188`
pins safety on "every handler reads its arguments at entry", which
`run.ts` neither documents nor enforces; a student's `on run` block that
reads `runArg(1)` after a `move` block gets 0.

`run.ts:1-5, 72-75` and `test.ts:543-549` still say handlers run on their
own fiber via MessageBus; since sprint 028 they run on the protocol fiber,
nested, and anything that blocks in a handler stalls PING/ESTOP.

## Remedy

- Bind the split array into the handler call (pass `parts` as a closure
  value, or push/pop a stack the nested bypass restores).
- Rewrite `onRun()`'s JSDoc: the handler runs on the wire's fiber; keep
  the wire alive by ticking; anything that sleeps stalls the wire.
- Fix the three factually wrong comments.

## Acceptance

- Host test (TS type-check plus a source pin): `runArg()` after a nested
  bypass returns the outer command's argument.
