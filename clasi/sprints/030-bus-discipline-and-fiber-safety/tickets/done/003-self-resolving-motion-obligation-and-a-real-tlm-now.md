---
id: '003'
title: Self-resolving motion obligation and a real TLM NOW
status: done
use-cases:
- SUC-003
depends-on:
- '002'
github-issue: ''
issue: code-review/clear-motion-obligation-on-the-fiber-loop-and-tlm-now.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Self-resolving motion obligation and a real TLM NOW

## Description

**CM-02.** `WireAdapter::resolvePendingIfDue()`
(`src/comms/wire_adapter.cpp:822-839`) clears
`motionObligationActive_` (sprint 016 ticket 003's fix), but is reached
only from `lastDone()`/`lastDoneReason()` (`wire_adapter.cpp:875,880`)
— i.e. from `replyAck`/`replyNack`/`STATUS`. Confirmed still live:
`Protocol::run()`'s loop (`protocol.cpp:683`) reads
`wireAdapter_.hasLiveMotionObligation()` directly every pass to decide
whether to call `tickDrive()`, and that method
(`wire_adapter.cpp:775-781`) reads `motionObligationActive_` and the
deadline without ever resolving a completed-but-unpolled motion first.
A host that sends `MOVE_X ... 30000 #7`, sees it finish in 3 s by some
means other than `STATUS`/`lastDone`, then sends a cleartext
`RUN:tour` gets it refused by `dispatchJob()`'s `motionOwner_ !=
kNone` gate (`protocol.cpp:426`) for the remaining 27 s, even though
the kernel has been idle the whole time.

**CM-04.** `WireAdapter::onTlm(TlmMode::kNow)`
(`wire_adapter.cpp:963-974`) acks `kOk` and does nothing — `mode_` is
deliberately never written for `kNow` (correct, per protocol.md S6.1),
but no code anywhere emits a one-shot frame in response either (`grep
-n kNow src/comms` finds only the mode-decode path). With telemetry
off, a host has no way to ask for one pose fix without subscribing to
a stream it would then have to unsubscribe from.

Both premises confirmed still live against current (post-sprint-029,
post-ticket-002) source.

## Remedy

- **CM-02**: Have `WireAdapter::hasLiveMotionObligation()` call
  `resolvePendingIfDue()` first (it is already a `const` method reached
  through a `mutable` state group, matching the existing
  `lastDone()`/`lastDoneReason()` pattern) — no new poll site needed in
  `protocol.cpp`'s `run()` loop, since that loop already calls
  `hasLiveMotionObligation()` every pass. This is additive to sprint
  016 ticket 003's fix, not a replacement: `lastDone()`/
  `lastDoneReason()` still resolve eagerly for a host that polls; this
  closes the case where nothing does. Update `src/DESIGN.md` §5's
  existing "Sprint 016 ticket 003" closure note to describe the
  additional trigger point (already drafted in this sprint's `design/`
  overlay).
- **CM-04**: Add a `oneShotDue_` flag to `WireAdapter`. `onTlm()` sets
  it on `TlmMode::kNow` without touching `mode_` (preserving the
  existing "does not change the current subscription" behavior).
  `Protocol::serviceOnce()` checks `oneShotDue_` alongside
  `telemetryEnabled()` each pass; when set, it builds and emits one
  `thdr`+`t` pair on both handlers via the same `buildSnapshot()`/
  `emitTelemetry()` pair the periodic path already uses (called one
  extra time, not duplicated), then clears the flag. If implementation
  finds this awkward for some `TlmMode` combination not yet exercised,
  the documented fallback is an honest `kUnimplemented` refusal (the
  same shape `TLM BUFFER` already uses) — state which outcome was
  chosen and why in the ticket's own notes.

## Acceptance Criteria

- [x] `hasLiveMotionObligation()` calls `resolvePendingIfDue()` before
      reading `motionObligationActive_`/the deadline.
- [x] A host test arms a short-timeout verb via the `WireAdapter`/
      `WireMockAdapter` test seam, lets it finish, and confirms
      `hasLiveMotionObligation()` reads `false` on the next call with
      **no** intervening `lastDone()`/`lastDoneReason()` call.
- [x] A host test confirms `onTlm(TlmMode::kNow)` sets the one-shot
      flag without changing `mode_`, and that the next `serviceOnce()`-
      equivalent pass produces exactly one frame pair (or, if the
      `kUnimplemented` fallback was chosen instead, that `TLM NOW`
      returns that code honestly).
- [x] `src/DESIGN.md` §5 is updated per this sprint's `design/` overlay
      text (apply it, adjusting for the actual implementation).
- [x] Existing `WireAdapter`/`WireMockAdapter`/`WireHandler` host suite
      passes unchanged, including the sprint 016 ticket 003 regression
      coverage for the original `onEstop()`/`onStop()`/eager-poll
      clearing paths. (See Implementation Notes below: three existing
      `test_wire_motion_completion.py` tests asserted the literal
      pre-fix gap this ticket closes — `has_live_motion_obligation()`
      reading `true` before an explicit poll — and had to be updated,
      not left "unchanged" byte-for-byte; every underlying resolution
      path (kStop/kTimeout/kEstop/kAborted, onEstop()/onStop()'s own
      clearing) they exercised is still covered and still passes.)
- [ ] Hardware (team-lead session, optional if host coverage is judged
      sufficient by the team-lead — this ticket's logic lives entirely
      in host-portable `wire_adapter.cpp`): a `MOVE_X ... #7` that
      completes early, followed by a cleartext `RUN:tour` with no
      intervening `STATUS`/`lastDone` poll, is accepted rather than
      refused for the remainder of the original verb's declared
      duration — MEASURED citation if run.

## Implementation Notes (programmer)

**CM-02 — which option, and why:** `hasLiveMotionObligation()` itself
now calls `resolvePendingIfDue()` before reading the deadline (the
first option the Remedy offered), not a new poll site in `run()`'s
loop — `run()` already calls `hasLiveMotionObligation()` every pass, so
no second call site was needed. One wrinkle the Remedy text didn't
spell out: `resolvePendingIfDue()` reaches `resolvePendingReason()`,
which (for a goal-directed pending motion) itself needs the same raw
deadline read `hasLiveMotionObligation()` used to BE — routing that
through the new self-resolving `hasLiveMotionObligation()` would
recurse forever. Fixed by splitting the old body out into a private
`motionObligationDeadlineLive()` (the pure, non-resolving deadline
check); `resolvePendingReason()` calls that directly, and
`hasLiveMotionObligation()` calls `resolvePendingIfDue()` then returns
`motionObligationDeadlineLive()`. Net effect on existing tests: three
`test_wire_motion_completion.py` tests asserted
`has_live_motion_obligation()` staying `true` immediately after a
goal-directed early completion, before any `last_done()`/
`last_done_reason()` poll — exactly the gap this ticket closes, so
those assertions necessarily flip to `false` post-fix. Updated (not
merely left broken): `test_move_x_reaching_its_own_goal_early_reports_stop`,
renamed `test_move_x_reaching_its_own_goal_early_then_poll_clears_the_obligation_flag`
to `test_move_x_reaching_its_own_goal_early_self_resolves_via_has_live_motion_obligation`,
and `test_obligation_window_narrows_after_natural_completion`. Added
`test_wheels_v_natural_timeout_self_resolves_via_has_live_motion_obligation_alone`
for the lease-style verb case the acceptance criterion asks for
literally (arm, let finish, poll `has_live_motion_obligation()` alone,
confirm `false`, confirm immunity to the clock-back wraparound trick).

**CM-04 — implement, not refuse, and why:** Gave `TLM NOW` a real
one-shot frame path rather than the `kUnimplemented` fallback. Named
the flag `oneShotTelemetryDue_` (Remedy's sketch used `oneShotDue_`)
and exposed a single `consumeOneShotTelemetry()` method that reads and
clears it in one call, rather than a separate peek + clear pair — the
caller that gets `true` back is unambiguously the one obligated to
emit, with no TOCTOU window even though this codebase is
single-fiber-cooperative and doesn't strictly need that guarantee.
`Protocol::serviceOnce()` checks it every pass, ungated by
`telemetryEnabled()` and by the periodic emission timer — required,
not optional: the entire point of `TLM NOW` per the issue text is
answering a pose-fix request while telemetry is OFF (`mode_ ==
kOff`), so gating on `telemetryEnabled()` would defeat it. No `TlmMode`
combination proved awkward; the fallback was not needed.

**Where this ticket stopped:** only `hasLiveMotionObligation()`/
`resolvePendingReason()` (CM-02) and `onTlm()`/`consumeOneShotTelemetry()`/
`Protocol::serviceOnce()`'s telemetry gate (CM-04) were touched.
`RunBridge`, the radio gates, `routeLine()`, and the full
`motionOwner_`/`jobOwnsMotion_` consolidation this sprint's design
overlay also discusses are sprint 033's, per this ticket's own scope
note — not touched here. Tickets 004 (glitch armor) and 005 (execRun
buffers) are untouched.

**Left UNVERIFIED (no hardware in this dispatch):** the hardware
acceptance criterion above (`MOVE_X ... #7` completing early, then a
cleartext `RUN:tour` accepted with no intervening poll) — the fix lives
entirely in host-portable `wire_adapter.cpp`/`protocol.cpp`, and the
host suite proves the same logical path (`resolvePendingIfDue()`
running from `hasLiveMotionObligation()`, `dispatchJob()`'s own
`motionOwner_ != kNone` gate is unchanged by this ticket and already
covered elsewhere), but nothing here ran on a real board. A team-lead
session with a board can settle it directly against the scenario in
the acceptance box above.

**Documentation debt (ticket 001 follow-up):** `src/DESIGN.md`'s "Bus
discipline" section (§7) still described the pre-ticket-001 `stepBusy`
bool with no `BusGuard` writeup, and the §8 component diagram's
`tickDrive after stepBusy=false` edge label was stale — ticket 001
shipped `BusGuard`/`Rig::busGuard`/the deferred `pendingOtosZero` write
without updating either. Rewrote the "Bus discipline" section against
the actual shipped `core/bus_guard.h`/`shims.cpp` (seven guarded OTOS
call sites: six named entry points plus `otosGet`'s own `case 8`, plus
`tickDrive()`'s own guard around `kernel.step()`; the deferred
`pendingOtosZero` write; the `test.ts`/`blocks/motion.ts` sampler
moves), fixed the diagram label, and fixed two more stale `stepBusy`
prose mentions found in §8 and §9 while in the area.

## Testing

- **Existing tests to run**: the existing `WireAdapter`/`WireMockAdapter`
  host harness (the same seam `stall_clear` and sprint 016 ticket 003's
  original fix were tested through); `tests/host/` full suite scoped to
  `wire_adapter.cpp`/`wire_handler.cpp` during implementation.
- **New tests to write**: the self-resolving-obligation test and the
  `TLM NOW` one-shot-frame test described above.
- **Verification command**: `uv run pytest tests/host/ -k "wire_adapter
  or tlm or motion_obligation"` during implementation; full `uv run
  pytest` at `close_sprint`.
