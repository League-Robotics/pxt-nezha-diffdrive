---
id: '001'
title: 'Wire timeout hardening: reject 0, clamp above 2^31-1, unify across all six
  motion verbs'
status: in-progress
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: wire-timeout-hardening.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Wire timeout hardening: reject 0, clamp above 2^31-1, unify across all six motion verbs

## Description

Two edge cases, one inconsistency, all in the `timeout`/`duration`
field every one of the six motion verbs
(`WHEELS_X`/`WHEELS_V`/`MOVE_X`/`MOVE_V`/`GO_TO_R`/`GO_TO_W`) carries
(code review R-06 + R-18, `wire-timeout-hardening.md`):

1. `WHEELS_X … timeout 0` decodes and acks `ok`, but
   `MotionEngine::wheelsX()`'s own lease-clamp
   (`if (timeoutMs > 0 && timeoutMs < lease) lease = timeoutMs;`,
   `motion_engine.cpp:81`) never fires when `timeoutMs == 0` — the
   kernel stays armed for the full dead-reckoned lease
   (`dominant / cruise * 1000`, often several seconds), while
   `WireAdapter::onWheelsX()`'s own `motionObligationDeadlineMs_ =
   nowMs_() + timeout` (`wire_adapter.cpp:380`) becomes `now`, so
   `hasLiveMotionObligation()` reports false immediately and
   `protocol.cpp`'s fiber stops ticking the kernel for this move. The
   robot does not move now, but the kernel command is still armed — the
   next unrelated tick (from a different verb, or a student's own
   `driveTick()` loop) resumes the stale command with no host visibility
   into why. Meanwhile `MOVE_X … timeout 0` is a different bug in a
   different direction (verify at execution time — `MotionEngine::moveX()`'s
   own timeout handling — and confirm/refine this description against
   the actual code path before fixing).
2. `parseUint32` admits the full `uint32_t` range (up to
   `4294967295`); nothing downstream currently prevents a
   `timeout`/`duration` above `2^31 - 1` reaching arithmetic that
   compares it as a signed 32-bit quantity, wrapping negative and
   re-triggering the ticket-011 starvation-kill pattern (an acked move
   dying at ~150 ms) for an input class no existing test reaches.

## Design Rationale

**Enforce once, at decode, not six times in each handler.** Add one
shared decode-time helper in `wire_handler.cpp` that every one of the
six motion verbs' `timeout`/`duration` field passes through before its
verb-specific decode logic runs: reject `0` (`Wire::Result::kRange`,
matching the existing precedent that `cruise <= 0` already refuses
rather than silently reinterpreting a nonsensical input), and clamp any
value above `2^31 - 1` down to it. This means `WireAdapter`'s own
obligation-window math and `MotionEngine`'s lease-clamp arithmetic never
see an out-of-range value — neither needs its own defensive check.
Reject (not clamp) was chosen for `0` specifically because both of
today's existing "0" behaviors (WHEELS_X's stale-lease lurch, MOVE_X's
silent no-op) are confirmed bugs, not two designs worth preserving
side by side — `err 3 #<id>` gives every host one unambiguous signal.
Clamp (not reject) was chosen for the upper bound because a host
sending an oversized timeout is asking for "run for a very long time,"
and capping serves that intent; rejecting would force hosts using a
large-sentinel pattern to learn this project's specific ceiling.
See `design/DESIGN.md` §4/§14 in this sprint's overlay for the full
Design Rationale entry.

## Acceptance Criteria

- [x] A shared decode-time helper in `wire_handler.cpp` rejects
      `timeout`/`duration == 0` (`kRange`) and clamps values above
      `2^31 - 1` down to it, applied uniformly to all six motion verbs
      before any verb-specific handler logic runs.
- [x] `WHEELS_X … timeout 0` no longer leaves a kernel lease armed with
      `hasLiveMotionObligation()` reporting false — confirmed by a host
      test that drives this exact R-06 sequence and asserts no
      obligation/lease mismatch (e.g. after the refused command, a
      subsequent unrelated tick does not resume a stale move).
- [x] `MOVE_X`'s existing `timeout 0` behavior is reconciled with the
      same reject-at-decode rule — investigate and document what
      `MotionEngine::moveX()` actually did before this ticket (this
      ticket's Description above states the WHEELS_X mechanism from
      direct source reading; MOVE_X's exact mechanism was not verified
      to the same depth during planning — confirm during execution and
      correct this ticket's own Description if it turns out to differ).
      Verified by direct reading of `motion_engine.cpp::moveX()`
      (`move_.deadline = nowMs() + timeoutMs;`, then `serviceMove()`'s
      `expired = (now - move_.deadline) >= 0` fires on the very next
      tick when `timeoutMs == 0`): the Description's characterization
      ("instant silent no-op") is accurate as written; no correction
      needed. GO_TO_R/GO_TO_W share this exact mechanism (both set
      `move_.deadline` the same way, directly or via `moveX()`).
- [x] A `timeout`/`duration` above `2^31 - 1` (up to `4294967295`) no
      longer reproduces the ticket-011 starvation pattern — a host test
      drives the exact R-18 sequence (a value above `2^31`) and asserts
      the move keeps running past ~150 ms instead of being killed.
- [x] The existing host-test boundary-value parametrize (currently
      maxing at 5000 ms) is extended to `0`, `2^31 - 1`, `2^31`, and
      `4294967295` across all six motion verbs, asserting the documented
      reject/clamp/unchanged behavior for each.
- [x] Values in the previously-tested range (1..5000 ms) are unchanged
      — no regression to `test_wire_motion_verbs.py`'s existing
      coverage.

## C++11 Gate Coverage

- **Inside the gate** (`tests/host/` compiles at C++20; both real
  targets compile at C++11): `wire_handler.h`/`.cpp` (the new shared
  clamp helper) and `wire_adapter.h`/`.cpp` (any handler-side read of
  the now-bounded value) — both already covered by
  `test_cxx11_syntax_gate.py`'s existing four-file list. Run the gate
  after this ticket's changes to confirm it still passes; no new file
  is added, so no new gate registration is needed.
- **Outside the gate**: none of this ticket's production changes touch
  a CODAL-bound file (`protocol.*`, the transports, `shims.cpp`), so
  this ticket has no target-only surface. A green host suite here IS
  meaningful evidence for this ticket's own changes — unusual among
  this sprint's tickets, worth stating explicitly rather than assuming
  the caveat applies uniformly.

## Testing

- **Existing tests to run**: `tests/host/test_wire_motion_verbs.py`,
  `tests/host/test_wire_grammar.py`, `tests/host/test_wire_reliability.py`
  — confirm no regression to previously-tested timeout/duration values
  or to decode/dispatch mechanics generally.
- **New tests to write**: boundary-value parametrize extension (`0`,
  `2^31 - 1`, `2^31`, `4294967295`) across all six motion verbs; a
  targeted R-06 sequence test (WHEELS_X, timeout 0, confirm no stale
  obligation/lease); a targeted R-18 sequence test (a value above
  `2^31`, confirm the move survives past ~150 ms).
- **Verification command**: `uv run pytest tests/host/ -k "timeout or
  wire_motion"` during development, then a full `uv run pytest` before
  marking this ticket done.
