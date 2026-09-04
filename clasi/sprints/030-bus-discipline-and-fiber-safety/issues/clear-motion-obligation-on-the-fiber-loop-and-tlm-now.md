---
status: in-progress
sprint: '030'
tickets:
- 030-003
---

# Clear the wire motion obligation on the fiber loop; make TLM NOW implement-or-refuse

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: CM-02, CM-04 ([comms](../../../docs/code-review/2026-09-02/raw/comms.md)). Triage #6.

## Description

**CM-02.** `resolvePendingIfDue()` now clears `motionObligationActive_`
(08-26 C-05's fix, `wire_adapter.cpp:798, 825`) but is reached only from
`lastDone()`/`lastDoneReason()`, i.e. from `replyAck`/`replyNack`/
`STATUS`. A host that sends `MOVE_X ... 30000 #7`, sees it finish in 3 s,
then sends a cleartext `RUN:tour` has the job refused for the remaining
27 s (`protocol.cpp:311, 553`) while the kernel is stepped the whole time.
`tools/robotlink.py`'s `send_until()` polls with sequenced verbs, which is
why the bench scripts never see it.

**CM-04.** `TLM NOW` acks `kOk` and emits nothing (`wire_adapter.cpp:924-934`);
no one-shot frame path exists anywhere (`grep -n kNow src/comms`). With
telemetry off it is the only way a host could ask for one pose fix without
subscribing.

## Remedy

- Have `hasLiveMotionObligation()` call `resolvePendingIfDue()` first, or
  expose `pollCompletion()` and call it at the top of `run()`'s loop.
  Update `src/DESIGN.md` section 5's C-05 closure note to say when the
  clear happens.
- `TLM NOW`: set a `oneShotDue_` that `serviceOnce()` checks beside
  `telemetryEnabled()` and emits one `thdr`+`t` pair on both handlers; or
  refuse `kUnimplemented` like `kBuffer` and say so in HELP.

## Acceptance

- Host test: a `MOVE_X` that completes with no further host line clears
  the obligation on the next fiber pass.
- Host test: `TLM NOW #n` produces exactly one frame pair (or an honest
  refusal).

## Related

- `i2c-fault-count-climbs-on-idle-bus.md` (open): idle-bus stepping is a
  candidate mechanism.
