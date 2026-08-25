---
id: '004'
title: 'WireAdapter: real motion-completion signal (lastDone/lastDoneReason)'
status: open
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: wire-motion-completion-signal.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# WireAdapter: real motion-completion signal (lastDone/lastDoneReason)

## Description

Closes `wire-motion-completion-signal.md` (code review R-23).
`WireAdapter::lastDone()`/`lastDoneReason()` (`src/wire_adapter.h:431-434`)
have permanently reported `0`/`kNone` since sprint 003 ticket 012 — a
deliberate, documented decision, explicitly flagged in that ticket's
own header comment as "a natural candidate to revisit once a real use
case needs `lastDone()`/`lastDoneReason()` to mean something." This
sprint's own closed-loop tooling is that use case: combined with
STATUS's `otos=0`-adjacent gaps, the only way a host can currently
observe "the move finished" is polling STATUS `active` at poll
granularity.

Independent of the Python tooling tickets (001-003) and of tickets
005-006 — no ordering constraint either way; this can run at any point
in the sequence.

**The design, worked out during sprint planning (full rationale in
`sprint.md`'s Design Rationale — read it before implementing, it rules
out two tempting alternatives):**

- Two lease-style verbs (WHEELS_V, WHEELS_X, MOVE_V) resolve
  done-vs-timeout-vs-superseded entirely from `WireAdapter`'s own
  *existing* `motionObligationActive_`/`motionObligationDeadlineMs_`
  bookkeeping (already present for `hasLiveMotionObligation()`) — no
  new dependency needed for these three verbs.
- The three goal-directed verbs (MOVE_X, GO_TO_R, GO_TO_W) additionally
  need to know whether the underlying `MotionEngine` move is still
  active when the lease deadline is reached, to distinguish "reached
  its own stop condition early" (`kStop`) from "ran out the clock"
  (`kTimeout`). This is the **one** genuinely new read: a thin,
  read-only, forward-declared `shims.cpp` bridge function —
  `engineMoveActive()` — matching the existing `engineWheelsX()`-style
  convention exactly (see `shims.cpp`'s existing block of forward
  declarations this file's own header comment lists).
  `WireAdapter` must **not** gain a stored reference to
  `MotionEngine`/`Rig` — that boundary is deliberate (see
  `wire_adapter.h`'s own comment on why `engine` stays a
  `shims.cpp`-owned singleton).
- `stall`/`estop` need **no new plumbing**: both already reach
  `WireAdapter` through the `diagValue()`/`computeFlags()` path this
  class already uses for STATUS's `flags=` and telemetry's `flags`
  column — `stall_halted` and `estopped` are already two of its eight
  diagnostic booleans (see `tests/host/golden_telemetry.py`'s
  `RAW_DIAG_BOOLEANS` for the existing ordinal mapping).
- `Wire::DoneReason` (`wire_handler.h`) gains one new enumerator,
  `kStall` (wire spelling `"stall"`) — purely additive, no existing
  wire consumer reads it today. `kAborted` ("the caller abandoned it")
  is read as **"superseded"**: a later motion verb replacing a
  still-live one, since `kStop`'s own comment already covers both
  "reached its own stop condition" and an explicit `stop()` call — no
  new enumerator needed for superseded.
- Out of scope for this ticket: generalizing `DoneReason` beyond these
  five reasons, a motion queue, or a completion history — see
  `sprint.md`'s Out of Scope.

## Acceptance Criteria

- [ ] `Wire::DoneReason` gains `kStall`; `doneReasonWireName()`
      (`wire_handler.cpp`) returns `"stall"` for it.
- [ ] `shims.cpp` gains one new thin, read-only, forward-declared free
      function (`engineMoveActive()` or equivalent) that
      `WireAdapter`/`wire_adapter.cpp` forward-declares and calls — no
      stored `MotionEngine`/`Rig` reference anywhere in
      `wire_adapter.h`/`.cpp`.
- [ ] `WireAdapter::lastDone()`/`lastDoneReason()` report real values
      for all six motion verbs (WHEELS_V, WHEELS_X, MOVE_X, MOVE_V,
      GO_TO_R, GO_TO_W), read fresh on every ack/nack (no cached copy),
      matching the existing S8.8 contract
      (`test_last_done_is_read_fresh_not_cached_across_calls`'s
      existing pattern in `tests/host/test_wire_reliability.py`, which
      tests the mock adapter — this ticket's new tests do the
      equivalent against the **real** `WireAdapter`).
- [ ] A motion that reaches its own stop condition before its
      deadline/lease expires reports `kStop`.
- [ ] A motion verb accepted while a previous one is still live reports
      `kAborted` for the superseded one.
- [ ] A lease-style verb's deadline elapses with nothing superseding it
      → `kTimeout`.
- [ ] The kernel's stall latch being set during a move → `kStall`.
- [ ] An ESTOP landing during a move → `kEstop`.
- [ ] Before any motion verb has ever completed, `lastDone()` reports
      `0` and `lastDoneReason()` reports `kNone` — the pre-existing
      "nothing completed yet" case is preserved, not broken by this
      ticket's new bookkeeping.
- [ ] `WireMockAdapter` (`tests/host/wire_mock_adapter.h`) and
      `tests/host/test_wire_reliability.py`'s existing mock-based tests
      are unaffected — this ticket changes the real `WireAdapter`, not
      the `Wire::Adapter` interface's mock test double's own behavior.
- [ ] `uv run pytest` (full suite) passes, including
      `tests/host/test_cxx11_syntax_gate.py`.

## Implementation Notes

- `lastDone()`'s `uint32_t` return value has no established meaning
  anywhere in this codebase or in `radio-robot-lib`'s own reference
  `DiffDriveAdapter` (which also leaves it permanently inert — this is
  genuinely new ground, not filling a spec gap). Sprint planning's own
  proposal: the accepted `id` of whichever motion verb most recently
  reached a terminal state, since that is what makes `ack <id>
  <lastDone> <reason>` legible to a future host distinguishing "the
  command I'm being acked for" from "the command that just finished."
  If a different convention seems clearly better once you're in the
  code, use judgment and note the deviation here — this is flagged as
  an open question in `sprint.md`, not a hard requirement.
- New host tests belong in `tests/host/` and should drive the **real**
  `WireAdapter` (the pattern `test_wire_motion_verbs.py`'s
  `wa`-fixture-based "real effect" tests already use — e.g.
  `test_wheels_v_real_effect_pure_forward`), not `WireMockAdapter`.
  Either extend `test_wire_motion_verbs.py` or add a new
  `test_wire_motion_completion.py` — implementer's choice; prefer a new
  file if the five-terminal-reason coverage would otherwise crowd an
  already-large existing file.
- Verify no cycle is introduced: `WireAdapter` → `shims.cpp` bridge →
  `MotionEngine`/kernel must remain strictly one-directional, matching
  every existing bridge function's own shape.

## C++11 Gate Coverage

- **Inside the gate** (`tests/host/` compiles at C++20; both real
  embedded targets compile at C++11): `wire_handler.h`/`.cpp` (the new
  `kStall` enumerator and wire-name mapping) and
  `wire_adapter.h`/`.cpp` (the new completion-tracking logic) — confirm
  these are already covered by `test_cxx11_syntax_gate.py`'s existing
  file list; if `shims.cpp` gains new code paths reachable from this
  ticket's new bridge function, confirm it is covered too (it should
  already be, as an existing gated file). Run the gate after this
  ticket's changes to confirm it still passes.
- **Outside the gate**: none of this ticket's changes touch a
  CODAL-bound-only file (`protocol.*`, the transports) — the new bridge
  function is a plain read with no CODAL API surface. A green host
  suite here should be meaningful evidence for this ticket's own
  changes, but this sprint's mandatory build-checkpoint ticket (007)
  still confirms it against a real target build, per this project's
  standing convention (a green host suite alone is never sufficient
  evidence a change compiles for the target).

## Testing

- **Existing tests to run**: `tests/host/test_wire_motion_verbs.py`,
  `tests/host/test_wire_reliability.py`, `tests/host/test_wire_grammar.py`
  — confirm no regression to existing motion-verb decode/dispatch or
  reliability-layer mechanics.
- **New tests to write**: host tests (real `WireAdapter`, not the mock)
  for each of the five terminal reasons — done, superseded, timeout,
  stall, estop — per this ticket's Acceptance Criteria, plus the
  fresh-not-cached read pattern and the pre-completion `0`/`kNone`
  default.
- **Verification command**: `uv run pytest tests/host/ -k "motion or
  reliability or completion"` during development, then the full
  `uv run pytest` before moving this ticket to done.
