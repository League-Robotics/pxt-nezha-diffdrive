---
id: '003'
title: Clear motionObligationActive_ when the pending motion resolves
status: done
use-cases: []
depends-on:
- '002'
github-issue: ''
issue: wire-motion-obligation-never-clears.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Clear motionObligationActive_ when the pending motion resolves

## Description

`WireAdapter::motionObligationActive_` (`wire_adapter.h:305`) is set
`true` by all six motion verbs (`wire_adapter.cpp:345,376,405,428,449,487`)
and is read by `protocol.cpp`'s fiber loop as its tick gate:
`if (wireAdapter_.hasLiveMotionObligation()) { tickDrive(); } else {
fiber_sleep(...); }`. It is currently cleared in exactly two places:
`onEstop()` (`:536`) and `onStop()` (`:568`). **Natural completion never
clears it** — `resolvePendingIfDue()` (`:619-626`) clears `pendingActive_`
and commits `lastDoneReason_` but leaves `motionObligationActive_` armed.
So after any wire motion verb, the protocol fiber keeps ticking the
kernel at 24 ms for the whole declared `timeout` regardless of when the
motion actually finished — up to `kMaxMotionTimeoutMs` (2^31-1 ms, 24.8
days) at the decode clamp for a goal-directed verb with a generous
timeout.

This depends on ticket 002 only in the sense that both touch adjacent
motion-completion machinery and the sprint sequences them together for
review coherence — this ticket's own change is confined to
`wire_adapter.cpp`/`.h` and does not require ticket 002's
`motion_engine.cpp` changes to compile or to be correct on its own
terms.

**Fix** (per the issue's own "What to change," which this ticket
implements verbatim): clear `motionObligationActive_ = false` in the two
places that already know the motion is over —

1. `resolvePendingIfDue()`, when it actually commits a resolution
   (`reason != Wire::DoneReason::kNone`, i.e. inside the block that
   currently sets `lastDoneId_`/`lastDoneReason_`/`pendingActive_ =
   false`) — this is the natural-completion path, the actual gap.
2. `forceResolvePending()`, when it actually commits (the existing
   `if (!pendingActive_) return;` guard already distinguishes a no-op
   call from a real one) — this covers the "a later verb supersedes a
   still-live earlier one" (`kAborted`) path, which already runs before
   the *new* verb re-arms `motionObligationActive_ = true` a few lines
   later in the same `onWheelsV`/`onWheelsX`/`onMoveX`/`onMoveV`/
   `onGoToR`/`onGoToW` handler, so ordering stays correct.

After this change, `onEstop()`'s and `onStop()`'s own existing explicit
`motionObligationActive_ = false;` lines become redundant with
`forceResolvePending()`'s new internal clear for `onStop()` (which calls
`forceResolvePending()` before its own explicit clear) — leave both as
they are; the duplication is harmless (idempotent) and removing
`onStop()`'s own line is not required by this ticket. `onEstop()`
deliberately does **not** call `forceResolvePending()` at all (see its
own comment: "deliberately NOT going through forceResolvePending()") —
it commits `pendingActive_ = false` inline and keeps its own explicit
`motionObligationActive_ = false;`, unaffected by this ticket.

The flag's meaning after this fix becomes "a motion is genuinely
outstanding, as far as the wire layer has NOTICED" — not "a motion was
issued and nothing has explicitly stopped or e-stopped it since." The
lazy nature of `resolvePendingIfDue()` (only invoked from `lastDone()`/
`lastDoneReason()`, which are polled on every ack/nack per protocol.md
S8.8) means the obligation can still outlive the *actual* motion by
however long it is before something next polls those two accessors —
this is a real, honest limitation, not a full fix; ticket 004
investigates whether it is enough to matter for the idle-I2C hypothesis.

## Acceptance Criteria

- [x] `resolvePendingIfDue()` clears `motionObligationActive_ = false`
      when it commits a resolution.
- [x] `forceResolvePending()` clears `motionObligationActive_ = false`
      when it commits a resolution.
- [x] `onEstop()`/`onStop()` are otherwise unchanged (their own explicit
      clears stay; no behavior change to the e-stop/stop paths).
- [x] A new host test proves: after a lease-style verb (e.g. `WHEELS_V`)
      naturally times out with nothing superseding it, calling
      `lastDoneReason()` (which internally calls `resolvePendingIfDue()`)
      causes `hasLiveMotionObligation()` to read `false` immediately
      afterward — today it stays `true` until an explicit `STOP`/`ESTOP`.
- [x] A new host test proves the same for a goal-directed verb (e.g.
      `MOVE_X`) reaching its own goal early (`kStop` via
      `engineMoveActive()` going false, mirroring
      `test_wire_motion_completion.py`'s existing
      `test_move_x_reaching_its_own_goal_early_reports_stop`).
- [x] Both new tests fail against the current (pre-fix) `wire_adapter.cpp`
      and pass after the fix.
- [x] All existing tests in `tests/host/test_wire_motion_completion.py`
      still pass unmodified (this fix must not change any `lastDone()`/
      `lastDoneReason()` outcome, only the obligation flag's own timing).

## Findings

Implemented as specified. `motionObligationActive_` (`wire_adapter.h`)
is now `mutable` (matching `pendingActive_`'s own pattern) and is
cleared inside both `resolvePendingIfDue()` and `forceResolvePending()`
(`wire_adapter.cpp`) immediately after each commits a resolution — after
`resolvePendingReason()` has already been read, preserving the exact
ordering both functions' existing comments document. `onEstop()`/
`onStop()` are byte-unchanged.

Two new host tests were added to `tests/host/test_wire_motion_completion.py`:
`test_wheels_v_natural_timeout_then_poll_clears_the_obligation_flag` and
`test_move_x_reaching_its_own_goal_early_then_poll_clears_the_obligation_flag`.
Both were verified (by temporarily reverting `wire_adapter.{h,cpp}` via
`git stash`) to fail against the pre-fix code and pass after restoring
the fix. Note on the WHEELS_V case: since a lease-style verb's natural
completion coincides exactly with its deadline elapsing,
`hasLiveMotionObligation()`'s own time gate already reads `false` the
instant `now` passes that deadline, with or without this fix — the
pre-fix bug there is that the *internal* flag stays armed forever after
that point (latent until something reactivates it). The test exposes
this by jumping the mock clock backward to a value still inside the
original lease window after the natural resolution has been polled —
numerically the same effect a real `millis()` wraparound eventually
produces on a long enough uptime. The MOVE_X test needs no such
trickery: it directly reproduces the ticket's motivating scenario (a
goal-directed move finishing well before its declared `timeout`) and is
the load-bearing regression proof.

`tests/host/test_wire_motion_completion.py tests/host/test_wire_motion_verbs.py`:
156 passed.

Doc comments updated in `wire_adapter.h` (class header, `hasLiveMotionObligation()`,
`resolvePendingIfDue()`/`forceResolvePending()` declarations, and the
`motionObligationActive_` member) and `src/DESIGN.md` §5 (optional, done
for consistency) to describe the new clearing behavior.

## Implementation Plan

### Approach

1. Edit `resolvePendingIfDue()` (`wire_adapter.cpp:619-626`): inside the
   `if (reason == ...)` early-return-guarded body (after the
   `reason == kNone` early return), add
   `motionObligationActive_ = false;` alongside the existing
   `lastDoneId_`/`lastDoneReason_`/`pendingActive_` commits.
2. Edit `forceResolvePending()` (`wire_adapter.cpp:628` onward): after its
   own `if (!pendingActive_) return;` guard, add
   `motionObligationActive_ = false;` where it commits its resolution
   (read the full function body first — it defers to
   `resolvePendingReason()` for a more specific reason before falling
   back to the caller's forced one; place the new line so it fires on
   every commit path, not just the fallback one).
3. Update the two functions' own doc comments (`wire_adapter.h:244-346`
   area) to describe the new clearing behavior — several existing
   comments there already reference "motionObligationActive_ below --
   clearing it first would..." ordering concerns; make sure the updated
   prose stays consistent with the actual new code, not just the old
   two-call-site story.

### Files to modify

- `src/comms/wire_adapter.cpp` — `resolvePendingIfDue()`,
  `forceResolvePending()`.
- `src/comms/wire_adapter.h` — doc comments describing when
  `motionObligationActive_` clears.
- New or extended test file, most naturally
  `tests/host/test_wire_motion_completion.py` (reuses its existing `wa`/
  `motion_verb_lib` fixtures from `test_wire_motion_verbs.py`, which
  already expose `has_live_motion_obligation()`, `set_now_ms()`,
  `feed()`, `last_done_reason()`, `service_move()`).

### Testing plan

- **New tests**: two tests as described in Acceptance Criteria, added to
  `tests/host/test_wire_motion_completion.py` alongside its existing
  `test_wheels_v_lease_elapses_with_nothing_superseding_reports_timeout`
  and `test_move_x_reaching_its_own_goal_early_reports_stop` (extend
  those scenarios with a `has_live_motion_obligation()` assertion after
  the resolving call, rather than writing wholly new setup).
- **Existing tests to run**:
  `uv run pytest tests/host/test_wire_motion_completion.py
  tests/host/test_wire_motion_verbs.py` (scoped to the wire-adapter
  motion-completion neighborhood this ticket touches).
- **Verification command**: `uv run pytest tests/host/test_wire_motion_completion.py`.

### Documentation updates

- `wire_adapter.h` doc comments (part of Acceptance Criteria above).
- `src/DESIGN.md` §5 (Wire adapter) is not required reading for this
  ticket to change, but if its prose describes `motionObligationActive_`
  as "cleared in exactly two places" (matching the issue's own framing),
  a one-line update noting the two NEW clearing points is welcome but not
  gating — ticket 006's stop-taxonomy table is the sprint's designated
  place for consolidating this kind of cross-cutting summary.
