---
id: '005'
title: Extract RunBridge from Protocol's inline RUN-command parking/dedupe/dispatch
status: in-progress
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: protocol-diet-runbridge-radio-enable-routeline.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Extract RunBridge from Protocol's inline RUN-command parking/dedupe/dispatch

## Description

**Verified 2026-09-05: this ticket has one fewer deliverable than the
issue text describes.** CM-14 ("`motionOwner_`/`jobOwnsMotion_`
collapse to one flag") already shipped in sprint 030:
`WireAdapter::jobOwnsMotion_` is gone, replaced by `externalOwner_` (a
`core/motion_owner.h::MotionOwner`, the same type `Protocol::
motionOwner_` uses), set exclusively via `WireAdapter::
setExternalOwner()` (`wire_adapter.cpp:411`) and checked at every
motion-verb intake. **Do not re-implement this — verify it and move
on.** No `run_bridge.*` file exists yet; the RUN-parking/dedupe/
dispatch logic genuinely lives inline in `protocol.h`/`.cpp` today,
confirmed by this reading.

Extract `RunBridge` (`src/comms/run_bridge.h/.cpp`, host-portable, no
`pxt.h` — the same shape `run_queue.h`'s `RunQueue` already has) with
`offer(text, len, nowMs)`, `dispatchOne()`, `currentText()`. Preserve
exactly: the 3 s same-text dedupe (applied at arrival, immune to
queueing); the `abort`/`clearestop` bypass rule (these two names skip
the queue and act immediately, regardless of `motionOwner_`); the
underlying `run_queue.h` ring's storage and drop counter (diag ordinal
28, corrected by ticket 003). `Protocol::dispatchJob()` calls
`RunBridge::dispatchOne()`/`currentText()` in place of the inline ring
read; the actual TypeScript dispatch call (`_registerRunDispatch()`/
`runAction0()`) is unchanged — `RunBridge` owns parking/dedupe/handoff
only, not the TS call itself.

**Do not touch `wire_adapter.cpp`, `motion_engine.*`, or `segment.h`**
— this ticket is confined to `comms/protocol.*` and the new
`comms/run_bridge.*`, so it has NO collision with sprint 031's unmerged
branch (which touches exactly those three files/areas).

## Acceptance Criteria

- [ ] `RunBridge` exists as a separate, host-portable type with its own
      host tests, independent of `Protocol` (sprint Success Criteria's
      own bar).
- [ ] The 3 s same-text dedupe and `abort`/`clearestop` bypass behave
      identically before and after (verified by test where the
      behavior is host-testable).
- [ ] `Protocol::dispatchJob()` calls `RunBridge`'s methods; no RUN-
      parking/dedupe state remains as a `Protocol` member.
  - [ ] CM-14 (`motionOwner_`/`jobOwnsMotion_`) is confirmed already
      resolved (sprint 030) — this ticket's own record states this
      explicitly rather than silently doing nothing on it.

## Testing

- **Existing tests to run**: any existing `run_queue.h` host tests (to
  confirm the ring's own behavior is untouched); code-review
  verification of `Protocol::dispatchJob()`'s unchanged TS-dispatch
  call (not host-testable — `pxt.h`).
- **New tests to write**: `tests/host/test_run_bridge.py` — `offer()`/
  `dispatchOne()`/`currentText()`, the dedupe window, and the
  abort/clearestop bypass, all exercised host-side with no `Protocol`
  in the link.
- **Verification command**: `uv run pytest tests/host/`
