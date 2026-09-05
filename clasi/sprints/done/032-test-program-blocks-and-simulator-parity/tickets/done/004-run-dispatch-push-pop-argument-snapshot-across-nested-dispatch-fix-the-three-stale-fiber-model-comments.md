---
id: '004'
title: 'RUN dispatch: push/pop argument snapshot across nested dispatch; fix the three
  stale fiber-model comments'
status: done
use-cases:
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: run-dispatch-contract-argument-snapshot-and-fiber-doc.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# RUN dispatch: push/pop argument snapshot across nested dispatch; fix the three stale fiber-model comments

## Description

Confirmed in current `src/blocks/run.ts`: `runParts` (line ~15) is a
bare module-level `let`, reassigned wholesale on every dispatch
(`wireRunDispatch()`'s callback, line ~50: `runParts = text.split(":")`).
`src/comms/protocol.h`'s own doc comments (accurate, and NOT changed by
this ticket) confirm the abort/clearestop bypass dispatches reentrantly,
NESTED inside whatever job is currently ticking — this is deliberate,
documented, sprint-028/030 behavior, kept so an abort never waits behind
the job it's meant to stop. Today, EVERY handler in `test.ts` happens to
read its arguments only at entry, before any reentrancy point, which is
exactly why nothing has broken yet — but this is a convention nothing
enforces, and `protocol.h`'s own comment admits as much ("every onRun()
handler in this package reads its arguments only at entry... never
later" — stated as an observation about today's handlers, not a
guarantee the mechanism provides). A future handler that reads
`runArg()`/`runArgText()` INSIDE its own tick loop (not just at entry)
would silently read whatever the most recently nested dispatch left in
`runParts`.

Also confirmed: THREE comments describe a fiber model that stopped
being true at sprint 028 (RUN handlers moved from a MessageBus-forked
second fiber to nested dispatch on the protocol fiber itself):
1. `run.ts` lines ~1-5 (`runParts`'s own declaration comment): "Safe as
   shared state because MessageBus delivers these events one at a time,
   each after the previous handler returns" — WRONG; RUN commands are
   no longer MessageBus events at all (this file's OWN
   `wireRunDispatch()` comment, ~20 lines below, correctly says so —
   the two comments in the same file currently contradict each other).
2. `run.ts` `onRun()`'s JSDoc (~line 74): "Handlers run on their own
   fiber, so a long test (a full tour) doesn't block the protocol." —
   WRONG; they run on the protocol fiber itself, nested.
3. `test/test.ts`'s `abort` handler's preamble comment (~line 589):
   "...even though that tour's own handler is mid-execution on its own
   fiber" — stale terminology from the same pre-028 model, though the
   surrounding sentence's SUBSTANCE (RUN handlers interleave) is
   already correct; needs rewording, not a logic change.

## Acceptance Criteria

- [x] `run.ts` gains a push/pop stack (or equivalent structurally-safe
      mechanism — a stack is the Design Rationale's chosen approach in
      `sprint.md`; deviate only with a documented reason) so that:
      `wireRunDispatch()`'s callback pushes the newly-split `parts`
      array before invoking any handler and pops it in a `finally` (or
      equivalent) after all handlers/any-handlers have run; `runArgText`/
      `runArgCount` read the TOP of the stack, not a bare module
      variable.
  - [x] `onRun()`'s existing public signature
        (`(name: string, handler: (arg: number) => void) => void`) is
        UNCHANGED — this is a purely internal mechanism change per the
        Design Rationale's explicit rejection of a signature change.
- [x] A host test demonstrates the property directly: simulate (via a
      TS-shape/source-pin test, since `tests/host/` cannot execute PXT)
      that after a nested dispatch pushes and pops its own frame, the
      stack's top-of-stack again matches the outer dispatch's own
      parts — pin the STACK'S OWN push/pop shape in source, since a
      full runtime simulation isn't available host-side (state this
      limitation explicitly in the test's own docstring, following
      `test_run_abort_source_pin.py`'s precedent).
- [x] The three comments identified above are corrected:
      1. `run.ts`'s `runParts` declaration comment (~lines 1-5) no
         longer claims MessageBus delivery; it should instead describe
         the actual safety mechanism this ticket introduces (the
         push/pop stack), superseding the OLD "MessageBus serializes
         it" reasoning entirely — don't just delete the wrong claim,
         replace it with what's now true.
      2. `onRun()`'s JSDoc (~line 74) states handlers run on the wire's
         own (protocol) fiber, nested inside whatever job or wire
         motion is already ticking, and that anything that sleeps or
         blocks in a handler body stalls the wire for that duration
         (cross-reference ticket 002's finding without duplicating its
         detail).
      3. `test.ts`'s `abort` handler's preamble comment (~line 589) is
         reworded to describe the actual mechanism (nested reentrant
         dispatch on one fiber), not "its own fiber."
- [x] No other stale "own fiber"/"MessageBus"/"forked fiber" claim is
      left in `run.ts` or `test.ts` — re-grep both files for
      `"own fiber"`/`MessageBus`/`forked` after the edit and confirm
      every remaining hit describes something ELSE accurately (e.g.
      `protocol.h`'s own comments about `emitLine()`'s caller-fiber
      contract are correct and out of scope — do not touch
      `protocol.h`/`protocol.cpp`, which this sprint's Architecture
      section confirms are already accurate).

## Testing

- **Existing tests to run**: `uv run pytest tests/host/test_run_abort_source_pin.py tests/host/` (full host suite, since this changes a core dispatch primitive many other host tests may source-pin against).
- **New tests to write**: a new `tests/host/test_run_dispatch_argument_snapshot.py` (or an extension of an existing file if a natural home exists — check first) pinning the push/pop stack's shape and the corrected comments' absence of the old wrong claims (regex asserting the OLD wrong phrases are gone AND the new correct ones are present, not just "some comment changed").
- **TS type-check**: `npx tsc --noEmit`.
- **Verification command**: `uv run pytest tests/host/ -k "run_dispatch or run_abort" -v`
