---
id: '003'
title: protocol.cpp tick integration for wire-issued motion
status: done
use-cases:
- SUC-003
depends-on:
- '001'
github-issue: ''
issue: caller-driven-tick-loop-for-diffdrive-pure-tick-model-design-sprint-002-issue.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# protocol.cpp tick integration for wire-issued motion

## Description

With the kernel's background fiber removed (ticket 001), a wire-issued
`MOVE`/`WHEELS` command has no student loop to keep ticking it —
without this ticket, `protocol.cpp`'s motion handlers would still
dispatch to `startMove()`/`setWheelsTimed()`/`driveTwistTimed()`
correctly, but the kernel would never actually step, so nothing would
move. Per sprint.md's Architecture ("Protocol / Comms" module) and
Design Rationale ("`protocol.cpp` ticks conditionally"), make the
protocol fiber its own bounded tick caller.

In `protocol.cpp`:

- Add local obligation tracking, mirroring `shims.cpp`'s own
  `moveActive`/deadline pattern: a `MOVE`-with-distance/angle obligation
  is live for as long as the existing `moving()`-equivalent state
  (`Rig::moveActive`, read via the existing shim surface) is true; a
  `MOVE`-with-time-stop or `WHEELS` obligation is live until a
  protocol-local tracked deadline (its own duration, mirroring
  `moveDeadline`) elapses.
- In `run()`'s loop: while an obligation is live, call `tickDrive()` in
  place of the loop's normal idle `fiber_sleep(kPollIntervalMs)` for
  that iteration — `tickDrive()`'s own absolute-deadline pacing sleep
  becomes the loop's sleep for that iteration (do not call both; that
  would double-sleep). Command dispatch (a line, if one arrived) and the
  TLM cadence check still run once per iteration as before, just at
  `tickDrive()`'s ~24 ms cadence while an obligation is live instead of
  the idle 5 ms poll. When no obligation is live, the loop reverts to
  its existing idle behavior unchanged (no ticking, 5 ms poll) — this
  sprint's tick model does not spin the kernel/I2C bus when nothing is
  commanded.
- `handleStop()`/`handleEstop()` must clear the local obligation
  tracking (not just call the existing `stopAll()`/`estopAll()` shims),
  so the loop reverts to idle cadence immediately on a wire-issued stop
  rather than continuing to tick until its tracked deadline naturally
  elapses.
- `handleMove()`/`handleWheels()` set the obligation when they dispatch
  (distance/angle → the existing `moveActive` state already covers it;
  time-stop `MOVE`/`WHEELS` → set the local tracked deadline from the
  duration already being passed to `setWheelsTimed`/`driveTwistTimed`).
- No change to the wire verb registry, line grammar, or any handler's
  existing decode/dispatch logic beyond the obligation bookkeeping
  above — this ticket is purely about *when the fiber ticks*, not
  *what a verb does*.

**Architecture-review guidance to carry into this implementation**
(APPROVE WITH CHANGES note from the sprint architecture review): keep
this obligation-tracking logic small and localized within
`protocol.cpp` (a couple of fields + a small helper deciding
idle-vs-tick, not sprawled across every handler) — `protocol.cpp`'s
core responsibility is still wire codec/dispatch; tick-cadence
participation is a bounded, secondary concern layered on top of it, not
a rewrite of its structure.

## Acceptance Criteria

- [x] `MOVE`(distance/angle), `MOVE`(time-stop), and `WHEELS` issued
      over the wire actually execute (the kernel steps) with the fiber
      pacer removed — not just accepted/dispatched.
- [x] The protocol fiber only calls `tickDrive()` while it has a live
      local motion obligation; when idle, it reverts to its existing
      5 ms `fiber_sleep`/no-tick behavior unchanged from sprint 001.
- [x] The loop never both calls `tickDrive()` and does its own idle
      `fiber_sleep` in the same iteration (no double-sleep).
- [x] `handleStop()`/`handleEstop()` clear the local obligation tracking
      in addition to calling the existing shims, so the loop returns to
      idle cadence immediately after a wire-issued stop.
- [x] `ESTOP`'s physical stop effect is unaffected by tick cadence (it
      already bypasses `step()` via `emergencyStopMotors()`'s direct
      port write, `nezha_port.cpp:80-85` — unchanged by this ticket).
- [x] An abandoned wire session mid-move (host disconnects, no `STOP`
      sent) is still caught by ticket 001's starvation watchdog within
      ~150 ms — this ticket does not need its own separate abandonment
      handling, since the watchdog already covers "nobody is ticking."
- [x] No change to the verb registry (`kVerbRegistry`), line grammar, or
      any binary payload shape.
- [x] Obligation-tracking state/logic is small and localized (a
      reviewer should be able to find "does the protocol loop need to
      tick right now" in one place).

## Testing

- **Existing tests to run**: none automated. Desk-review this ticket's
  handler/loop changes against sprint 001's existing `protocol.cpp`
  logic to confirm no verb dispatch, codec, or registry behavior
  changed — only the loop's idle-vs-tick branching and the two stop
  handlers' obligation-clearing.
- **New tests to write**: none automated. Wire-level correctness (a
  host issuing `MOVE`/`WHEELS` actually moves the robot; `STOP`/`ESTOP`
  responsiveness during an active move; abandoned-session watchdog
  coverage) is covered by sprint.md's Test Strategy deferred hardware
  pass, exercised the same way sprint 001's wire verbs were verified
  (a host script over USB serial via `mbdeploy`/vevov). Do not block
  this ticket on that pass.
- **Verification command**: none (no test runner). Verify by code
  review against this ticket's acceptance criteria.
