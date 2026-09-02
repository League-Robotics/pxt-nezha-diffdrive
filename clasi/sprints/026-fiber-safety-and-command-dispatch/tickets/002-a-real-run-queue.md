---
id: '002'
title: "A real RUN queue"
status: open
use-cases:
- SUC-002
depends-on: []
github-issue: ''
issue: fiber-safety-and-command-dispatch.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# A real RUN queue

## Description

`runSlots_[4][48]` + `nextRunSlot_` (`src/comms/protocol.h:142-145`) is
a write cursor with no read cursor, no occupancy tracking, and no
overflow signal. A burst of RUN commands arriving during a long tour
silently overwrites text a pending handler has not yet read — the
exact failure the ring's own comment claims to prevent. The 3 s
same-text dedupe (`handleRun()`, `protocol.cpp`) exists only to paper
over the missing occupancy tracking, and as a side effect it makes
sending the identical command twice inside 3 s silently impossible —
which is exactly the shape `tools/turn_sweep.py` sends. Full analysis:
`clasi/issues/fiber-safety-and-command-dispatch.md` §2 and "Proposed
fix" step 2.

Replace the write-cursor with a real ring: a header-only queue in
`src/comms/run_queue.h`, `head`/`tail`/`count` plus a `dropped`
counter, 8 slots — following the precedent
`src/core/heading_wrap.h` and `src/core/encoder_glitch_armor.h` set
for extracting a small, host-portable, dependency-free core out of a
CODAL-bound file (`protocol.h`/`protocol.cpp` include `pxt.h`
transitively and cannot be host-compiled directly; the pure ring logic
can be, the same way `heading_wrap.h`'s pure function is). `handleRun()`
switches to enqueue instead of overwrite; `dropped` is surfaced through
the existing `diagValue()` ordinal table (see `src/shims.cpp`'s
`diagValue()` switch, currently through ordinal 19 — this ticket adds
the next free ordinal) so overflow becomes visible instead of silent.
The 3 s dedupe window can then shrink or be removed, since the queue
itself is what was actually missing.

**This ticket is scoped to the queue only — no fiber or dispatch
change.** `handleRun()` still raises the same MessageBus event it does
today; the RUN handler still runs on its own forked fiber (ticket 003's
job, gated on ticket 001's hardware confirmation, is to change that).
This ticket is fully host-testable without any CODAL toolchain.

## Acceptance Criteria

- [ ] `src/comms/run_queue.h` — header-only, `<cstdint>`/`<cstring>` (or
      equivalent) only, no `pxt.h`, no CODAL types — a ring with 8
      slots, each holding up to 48 bytes (name + args + NUL, matching
      the existing `kRunTextBytes`), plus `head`/`tail`/`count` and a
      `dropped` counter that increments (and saturates, does not wrap)
      when `enqueue()` is called on a full ring.
- [ ] `enqueue()` preserves arrival order; `dequeue()` returns slots in
      the order they were enqueued (FIFO), matching the ring's own
      contract — no dropped/overwritten in-flight text under any
      sequence of interleaved enqueue/dequeue calls that never exceeds
      8 outstanding entries.
- [ ] `handleRun()` (`src/comms/protocol.cpp`) is rewired to call
      `enqueue()` instead of writing directly into `runSlots_`/
      `nextRunSlot_`; `runSlots_`/`nextRunSlot_` are removed once the
      queue replaces them (not left as dead code).
- [ ] `dropped` is surfaced through `diagValue()`'s ordinal table at
      the next free ordinal (confirm the current highest ordinal in
      `src/shims.cpp`'s `diagValue()`/`setKernelValue()`/
      `getConfigValue()` switches before assigning — do not silently
      collide with a ordinal ticket 003 or an unrelated change may also
      want).
- [ ] `runText()`'s public contract (`Protocol::runText(int slot)`,
      returning the payload text for a MessageBus event's slot value)
      is preserved or replaced with an equivalent the TS layer's
      `runCommandText()` shim can still use unchanged — no change to
      `src/blocks/run.ts`'s dispatcher shape in this ticket.
- [ ] The 3 s same-text dedupe window (`kRunDedupeMs`,
      `lastRunText_`/`lastRunMs_`) may shrink or be removed now that
      the queue itself prevents silent loss; if kept, document in the
      ticket's completion notes why it is still needed alongside the
      queue (e.g. still protects against a genuine double-send from a
      host retry policy) rather than leaving both mechanisms in place
      with no stated reason.
- [ ] A host test proves `tools/turn_sweep.py`'s pattern (the identical
      command sent twice within a few seconds) is no longer
      categorically suppressed once the dedupe window is adjusted.
- [ ] `uv run pytest` (full host suite) passes.
- [ ] No new comment names a sprint, a ticket, an `R-NN` code, or any
      `.md` filename — the archaeology marker budget is at 388/388
      with zero slack (`test_archaeology_marker_budget.py`). Describe
      the ring's mechanism in `run_queue.h`'s own comments; put issue
      references in the commit message only.
- [ ] `pxt.json`'s `files[]` includes `src/comms/run_queue.h` if PXT's
      manifest completeness check requires header-only files to be
      listed explicitly (confirm against `test_pxt_manifest_completeness.py`'s
      actual rule — some host-portable headers in this tree are
      reached only via `#include` from a listed `.cpp`, not listed
      themselves; match whichever convention that test enforces).

## Implementation Plan

**Approach**: Write `run_queue.h` first as a pure, host-testable ring
(mirroring `heading_wrap.h`'s doc-comment shape: what it is, why it's
host-portable, what test exercises it, and — since this one has no
natural `.cpp` — a syntax-check translation unit following
`heading_wrap_syntax_check.cpp`'s precedent if `test_cxx11_syntax_gate.py`
requires one for new headers). Prove FIFO order and drop-counting with
a host test before touching `protocol.cpp`. Then rewire `handleRun()`
to use it, delete `runSlots_`/`nextRunSlot_`, and wire `dropped`
through to `diagValue()`.

**Files to create**: `src/comms/run_queue.h`,
`tests/host/test_run_queue.py` (or equivalent), a syntax-check
translation unit if the existing gate requires one for a new
header-only module.

**Files to modify**: `src/comms/protocol.h` (remove `runSlots_`/
`nextRunSlot_`, add the queue member), `src/comms/protocol.cpp`
(`handleRun()`, `runText()`), `src/shims.cpp` (`diagValue()`'s new
ordinal), `pxt.json` (if required per the acceptance criterion above).

**Files NOT to modify**: `src/blocks/run.ts` (dispatcher shape is
ticket 003's concern), `src/comms/wire_adapter.*` (no ownership
tracking needed for this ticket).

## Testing

- **Existing tests to run**: full `uv run pytest`, especially any
  existing test that exercises `handleRun()`/`runText()` today (check
  for a pre-existing RUN-dispatch host test before assuming there is
  none).
- **New tests to write**: `run_queue.h`'s FIFO-order and drop-counting
  behavior under a host test that never needs CODAL; a regression test
  proving a burst of more than 8 unread commands increments `dropped`
  rather than corrupting an in-flight slot's text; a test (or a
  documented manual confirmation) that `turn_sweep.py`'s repeated-
  identical-command pattern now succeeds.
- **Verification command**: `uv run pytest tests/host/test_run_queue.py`
  (or wherever the new tests land) plus the full suite,
  `uv run pytest`.
