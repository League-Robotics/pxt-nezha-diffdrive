---
id: '003'
title: Self-resolving motion obligation and a real TLM NOW
status: open
use-cases: [SUC-003]
depends-on: ['002']
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

- [ ] `hasLiveMotionObligation()` calls `resolvePendingIfDue()` before
      reading `motionObligationActive_`/the deadline.
- [ ] A host test arms a short-timeout verb via the `WireAdapter`/
      `WireMockAdapter` test seam, lets it finish, and confirms
      `hasLiveMotionObligation()` reads `false` on the next call with
      **no** intervening `lastDone()`/`lastDoneReason()` call.
- [ ] A host test confirms `onTlm(TlmMode::kNow)` sets the one-shot
      flag without changing `mode_`, and that the next `serviceOnce()`-
      equivalent pass produces exactly one frame pair (or, if the
      `kUnimplemented` fallback was chosen instead, that `TLM NOW`
      returns that code honestly).
- [ ] `src/DESIGN.md` §5 is updated per this sprint's `design/` overlay
      text (apply it, adjusting for the actual implementation).
- [ ] Existing `WireAdapter`/`WireMockAdapter`/`WireHandler` host suite
      passes unchanged, including the sprint 016 ticket 003 regression
      coverage for the original `onEstop()`/`onStop()`/eager-poll
      clearing paths.
- [ ] Hardware (team-lead session, optional if host coverage is judged
      sufficient by the team-lead — this ticket's logic lives entirely
      in host-portable `wire_adapter.cpp`): a `MOVE_X ... #7` that
      completes early, followed by a cleartext `RUN:tour` with no
      intervening `STATUS`/`lastDone` poll, is accepted rather than
      refused for the remainder of the original verb's declared
      duration — MEASURED citation if run.

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
